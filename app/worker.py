from __future__ import annotations

import datetime
import logging

from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from google.cloud import firestore

from app.core import _get_firestore_client

logger = logging.getLogger(__name__)

class OpteryxConnection:
    def __init__(self):
        self.connection = None

    def __enter__(self):
        import opteryx  # local import so module doesn't become a hard dependency for tests
        self.connection = opteryx.connect()
        return self.connection
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self.connection:
            self.connection.close()

def _doc_ref_for_handle(db: Any, handle: str):
    return db.collection("jobs").document(handle)


def process_statement(
    statement_handle: str,
    batch_size: int = 100_000,
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
    sql = job.get("sqlText")
    if not sql:
        doc_ref.update({"status": "FAILED", "error": "missing sqlText"})
        return

    # update to EXECUTING
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    doc_ref.update({"status": "EXECUTING", "updated_at": now, "progress": 0})

    try:
        with OpteryxConnection() as conn:
            cursor = conn.cursor()
            df = cursor.execute_to_arrow(sql)
            statistics = cursor.stats


        # Iterate batches and write parquet files
        part_index = 0
        # opteryx.query_to_arrow returns a pyarrow.Table. Use pyarrow's
        # `to_batches` with the `max_chunksize` kwarg and convert the
        # returned RecordBatch objects into Tables before writing.
        for batch in df.to_batches(max_chunksize=batch_size):
            # Convert RecordBatch to Table
            table = pa.Table.from_batches([batch])

            # Compose path with zero-padded indices
            part_name = f"part_{part_index:04d}.parquet"
            gcs_path = f"gs://{bucket}/{statement_handle}/{part_name}"

            # Use pyarrow to write directly to GCS using the GCS file system
            # Let pyarrow infer the filesystem based on the URI and write the
            # parquet file directly to GCS.
            pq.write_table(table, gcs_path)

            part_index += 1

        doc_ref.update({"status": "COMPLETED", "updated_at": firestore.SERVER_TIMESTAMP, "statistics": statistics})
        return statistics

    except Exception as exc:  # pragma: no cover - errors bubble for production
        logger.exception("Error executing statement %s", statement_handle)
        doc_ref.update({"status": "FAILED", "error": str(exc), "updated_at": firestore.SERVER_TIMESTAMP})
        raise


__all__ = ["process_statement"]
