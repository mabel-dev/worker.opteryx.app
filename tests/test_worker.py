import json

import sys
import types
import pyarrow as pa
import pyarrow.parquet as pq

# Create a minimal 'opteryx' package with the attributes used by app.worker so
# importing app.worker does not fail in environments where the real package
# isn't installed.
opteryx_pkg = types.ModuleType("opteryx")
opteryx_pkg.register_store = lambda *a, **k: None
opteryx_pkg.connect = lambda *a, **k: None
opteryx_pkg.connectors = types.ModuleType("opteryx.connectors")
iceberg_module = types.ModuleType("opteryx.connectors.iceberg_connector")
setattr(iceberg_module, "IcebergConnector", type("IcebergConnector", (), {}))
setattr(opteryx_pkg.connectors, "iceberg_connector", iceberg_module)
sys.modules["opteryx"] = opteryx_pkg
sys.modules["opteryx.connectors"] = opteryx_pkg.connectors
sys.modules["opteryx.connectors.iceberg_connector"] = iceberg_module
from app.worker import process_statement


class FakeSnapshot:
    def __init__(self, data):
        self.exists = True
        self._data = data

    def to_dict(self):
        return self._data


class FakeDocRef:
    def __init__(self, data):
        self._data = data
        self.updates = []

    def get(self):
        return FakeSnapshot(self._data)

    def update(self, payload):
        self.updates.append(payload)


class FakeCollection:
    def __init__(self, data):
        self._data = data

    def document(self, _handle):
        return FakeDocRef(self._data)


class FakeDB:
    def __init__(self, data):
        self._data = data

    def collection(self, _name):
        return FakeCollection(self._data)


def make_table(num_rows: int):
    # Basic table with a single int column
    arr = pa.array(list(range(num_rows)))
    return pa.Table.from_pydict({"id": arr})


def test_process_statement_single_batch(monkeypatch):
    # Sample job
    job = {
        "execution_id": "3ef2a90c-357f-4f89-96d5-69e832008839",
        "sqlText": "SELECT 1",
        "status": "queued",
        "submitted_by": "bastian",
    }

    db = FakeDB(job)

    # monkeypatch the firestore client getter
    monkeypatch.setattr("app.worker._get_firestore_client", lambda: db)

    # create a small table and monkeypatch opteryx.query_to_arrow
    table = make_table(10)

    class FakeOpteryx:
        @staticmethod
        def query_to_arrow(_sql):
            return table

    monkeypatch.setitem(globals(), "opteryx", FakeOpteryx)
    monkeypatch.setattr("app.worker.opteryx", FakeOpteryx, raising=False)

    writes = []

    def fake_write_table(_table_arg, path, **_kwargs):
        writes.append(path)

    monkeypatch.setattr(pq, "write_table", fake_write_table)

    # Run the worker
    process_statement(job["execution_id"], batch_size=100_000, bucket="opteryx_results")

    # We should have written a single part
    assert len(writes) == 1
    assert writes[0].endswith("part_0000.parquet")


def test_process_statement_multiple_batches(monkeypatch):
    # Create job
    job = {
        "execution_id": "test-multi",
        "sqlText": "SELECT 1",
        "status": "queued",
        "submitted_by": "bastian",
    }
    db = FakeDB(job)
    monkeypatch.setattr("app.worker._get_firestore_client", lambda: db)

    # create a table with 25k rows and test with 10k batch size => expect 3 parts
    table = make_table(25_000)

    class FakeOpteryx:
        @staticmethod
        def query_to_arrow(_sql):
            return table

    monkeypatch.setattr("app.worker.opteryx", FakeOpteryx, raising=False)

    writes = []

    def fake_write_table(_table_arg, path, **_kwargs):
        writes.append(path)

    monkeypatch.setattr(pq, "write_table", fake_write_table)

    process_statement(job["execution_id"], batch_size=10_000, bucket="opteryx_results")
    assert len(writes) == 3
    assert writes[0].endswith("part_0000.parquet")
    assert writes[1].endswith("part_0001.parquet")
    assert writes[2].endswith("part_0002.parquet")


def test_manifest_written(monkeypatch):
    # Create job
    job = {
        "execution_id": "manifest-test",
        "sqlText": "SELECT 1",
        "status": "queued",
        "submitted_by": "bastian",
    }
    db = FakeDB(job)
    monkeypatch.setattr("app.worker._get_firestore_client", lambda: db)

    # create a small table and monkeypatch opteryx.query_to_arrow
    table = make_table(10)

    class FakeOpteryx:
        @staticmethod
        def query_to_arrow(_sql):
            return table

    monkeypatch.setattr("app.worker.opteryx", FakeOpteryx, raising=False)

    writes = []

    def fake_write_table(_table_arg, path, **_kwargs):
        writes.append(path)

    monkeypatch.setattr(pq, "write_table", fake_write_table)

    # Fake filesystem for manifest write capture
    class FakeOutputStream:
        def __init__(self, path, storage):
            self.path = path
            self.storage = storage
            self.data = b""

        def write(self, b):
            self.data += b

        def close(self):
            pass

    class FakeFS:
        def __init__(self):
            self.writes = {}

        def open_output_stream(self, path):
            out = FakeOutputStream(path, self.writes)
            self.writes[path] = out
            return out

    fake_fs = FakeFS()

    def fake_from_uri(uri):
        # Return our fake filesystem and a path relative to it (strip scheme)
        path = uri.split("gs://", 1)[1]
        return fake_fs, path

    monkeypatch.setattr(pa.fs.FileSystem, "from_uri", fake_from_uri)

    process_statement(job["execution_id"], batch_size=100_000, bucket="opteryx_results")

    # Manifest should have been written in addition to a part file
    assert any(p.endswith("part_0000.parquet") for p in writes)
    # The manifest path should end with manifest.json; it is captured in the fake FS writes
    # Find the fake FS used above by calling from_uri again
    _, path = pa.fs.FileSystem.from_uri(f"gs://opteryx_results/{job['execution_id']}/manifest.json")
    assert "manifest.json" in path
    manifest_out = fake_fs.writes.get(path)
    assert manifest_out is not None
    manifest = json.loads(manifest_out.data.decode("utf-8"))
    assert manifest["total_parts"] == 1
    assert manifest["total_rows"] == 10
    assert "columns" in manifest
    assert manifest["columns"][0]["name"] == "id"
    assert "int" in manifest["columns"][0]["type"]
    # Ensure the document update included a total size estimate that covers
    # the final part; we expect it to be > 0 for a non-empty result set.
    # Find the last update that contains 'status' == 'COMPLETED' and check
    # the 'total_size_estimate' value.
    docref = db.collection("jobs").document(job["execution_id"])
    # There may be multiple updates; find the completed update
    completed_updates = [u for u in docref.updates if u.get("status") == "COMPLETED"]
    assert completed_updates, "No COMPLETED update found"
    completed = completed_updates[-1]
    assert "total_size_estimate" in completed
    assert completed["total_size_estimate"] > 0
