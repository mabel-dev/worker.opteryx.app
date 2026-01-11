from __future__ import annotations

import datetime
import os
import sys
from typing import Any
from typing import List
from typing import Tuple

import opteryx
import orjson
import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import firestore
from opteryx.connectors import OpteryxConnector
from opteryx_catalog import OpteryxCatalog
from orso.logging import get_logger

from app.core import _get_firestore_client

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../opteryx-core")))
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../pyiceberg-firestore-gcs"))
)


logger = get_logger()

SIZE_THRESHOLD_BYTES = 256 * 1024 * 1024  # 256 MB
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE")
BUCKET_NAME = os.environ.get("GCS_BUCKET")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")

opteryx.set_default_connector(
    OpteryxConnector,
    catalog=OpteryxCatalog,
    firestore_project=GCP_PROJECT_ID,
    firestore_database=FIRESTORE_DATABASE,
    gcs_bucket=BUCKET_NAME,
)


def _doc_ref_for_handle(db: Any, handle: str):
    return db.collection("jobs").document(handle)


def _estimate_table_bytes(table: pa.Table) -> int:
    """Estimate the memory size of a pyarrow Table by summing buffer sizes.

    This avoids making expensive copies (e.g. to_pandas()) and should be
    accurate enough for deciding when to flush to disk.
    """
    total = 0
    for col in table.itercolumns():
        # ChunkedArray
        for chunk in col.chunks:
            for buf in chunk.buffers():
                if buf is not None:
                    total += buf.size
    return total


def _write_parquet_table(table: pa.Table, gcs_path: str) -> int:
    """Write a pyarrow Table to the given gs:// path using zstd and disabled statistics.

    Returns the number of bytes written if available (otherwise -1).
    """
    # Disable writing statistics, avoid dictionary encoding (can slow writes),
    # and prefer Parquet v2 data page format for better I/O behavior.
    pq_write_kwargs = dict(
        compression="zstd",
        compression_level=2,
        write_statistics=False,
        use_dictionary=False,
        data_page_version="2.0",
    )
    pq.write_table(table, gcs_path, **pq_write_kwargs)
    # We don't have a good way to read the remote file's bytes without extra
    # filesystem APIs here. Return -1 to indicate unknown.
    return -1


def _write_manifest(manifest: dict, manifest_path: str):
    """Write a JSON manifest to the given gs:// path.

    We use pyarrow's filesystem inference to write the bytes directly.
    """
    # Get filesystem and relative path from URI
    fs, path = pa.fs.FileSystem.from_uri(manifest_path)
    # Write JSON to the output stream
    with fs.open_output_stream(path) as out:
        out.write(orjson.dumps(manifest))


def process_statement(
    statement_handle: str,
    batch_size: int = 50_000,
    bucket: str = "opteryx_results",
):
    """
    Load a job from Firestore, set it to EXECUTING, run the query using opteryx,
    and write results as parquet files into Google Cloud Storage in batches of
    `batch_size` rows.

    On success the Firestore document status will be set to COMPLETED.
    On errors, the status will be set to FAILED and the error stored on the document.
    """
    db = _get_firestore_client()
    if db is None:
        raise RuntimeError("Firestore client unavailable")

    doc_ref = _doc_ref_for_handle(db, statement_handle)
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"No job found for handle: {statement_handle}")

    job = doc.to_dict()
    sql = job.get("sql_text")
    if not sql:
        doc_ref.update(
            {
                "status": "FAILED",
                "error": "missing sql_text",
                "updated_at": firestore.SERVER_TIMESTAMP,
                "finished_at": firestore.SERVER_TIMESTAMP,
            }
        )
        return

    # update to EXECUTING
    doc_ref.update(
        {
            "status": "EXECUTING",
            "updated_at": firestore.SERVER_TIMESTAMP,
            "started_at": firestore.SERVER_TIMESTAMP,
        }
    )

    total_size_estimate = 0

    try:
        with opteryx.connect() as conn:
            cursor = conn.cursor(qid=statement_handle)
            batches = cursor.execute_to_arrow_batches(sql, batch_size=batch_size)

            # Iterate batches and write parquet files. We'll accumulate batches
            # (each batch is at most `batch_size` rows) until the accumulated
            # Table is >= SIZE_THRESHOLD_BYTES, then we'll write that part.
            part_index = 0
            buffered_batches: List[pa.RecordBatch] = []
            buffered_rows = 0
            parts: List[Tuple[str, int, int]] = []  # (filename, rows, approx_size)

            for batch in batches:
                buffered_batches.append(batch)
                buffered_rows += batch.num_rows

                # Estimate bytes for the accumulated buffered batches
                buffered_table = pa.Table.from_batches(buffered_batches)
                buffered_bytes = _estimate_table_bytes(buffered_table)

                # When we exceed threshold (or at least one batch was collected and
                # this batch pushed us over), flush to a parquet part file.
                if buffered_bytes >= SIZE_THRESHOLD_BYTES:
                    part_name = f"part_{part_index:04d}.parquet"
                    gcs_path = f"gs://{bucket}/{statement_handle}/{part_name}"
                    # Write the parquet file with zstd compression and disabled statistics
                    _write_parquet_table(buffered_table, gcs_path)
                    parts.append((part_name, buffered_rows, buffered_bytes))
                    # Reset buffers
                    buffered_batches = []
                    buffered_rows = 0
                    part_index += 1
                    total_size_estimate += buffered_bytes

            # At the end write any remaining buffered batches as the final part.
            if buffered_batches:
                last_table = pa.Table.from_batches(buffered_batches)
                part_name = f"part_{part_index:04d}.parquet"
                gcs_path = f"gs://{bucket}/{statement_handle}/{part_name}"
                _write_parquet_table(last_table, gcs_path)
                last_table_size = _estimate_table_bytes(last_table)
                parts.append((part_name, buffered_rows, last_table_size))
                total_size_estimate += last_table_size

            telemetry = cursor.telemetry

        total_rows = sum(rows for _, rows, _ in parts)
        columns = [{"name": f.name, "type": f.type} for f in cursor.schema.columns]

        # Write manifest with metadata next to the parquet files
        manifest = {
            "parts": [
                {
                    "path": f"gs://{bucket}/{statement_handle}/{pname}",
                    "rows": rows,
                    "approx_size": approx_size,
                }
                for pname, rows, approx_size in parts
            ],
            "total_parts": len(parts),
            "total_rows": total_rows,
            "total_size_estimate": total_size_estimate,
            "compression": "zstd",
            "compression_level": 2,
            "write_statistics": False,
            "columns": columns,
            "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
        manifest_path = f"gs://{bucket}/{statement_handle}/manifest.json"
        _write_manifest(manifest, manifest_path)

        doc_ref.update(
            {
                "status": "COMPLETED",
                "updated_at": firestore.SERVER_TIMESTAMP,
                "finished_at": firestore.SERVER_TIMESTAMP,
                "telemetry": telemetry,
                "result_manifest": manifest_path,
                "total_rows": total_rows,
                "columns": columns,
                "total_size_estimate": total_size_estimate,
            }
        )

        execution_log = telemetry
        execution_log["statement_handle"] = statement_handle
        execution_log["statement"] = sql
        execution_log["result_manifest"] = manifest
        logger.audit(execution_log)

        return

    except Exception as exc:  # pragma: no cover - errors bubble for production
        logger.error(f"Error executing statement {statement_handle}")

        doc_ref.update(
            {
                "status": "FAILED",
                "error": str(exc),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "finished_at": firestore.SERVER_TIMESTAMP,
            }
        )
        raise


__all__ = ["process_statement"]
