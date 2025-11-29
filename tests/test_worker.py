import sys
import os

sys.path.insert(0, os.getcwd())

from app import worker as worker_module


class FakeDoc:
    def __init__(self, data: dict):
        self._data = data
        self.exists = True

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, data: dict):
        self.data = dict(data)
        self.updates = []

    def get(self):
        return FakeDoc(self.data)

    def update(self, payload: dict):
        self.updates.append(payload)
        self.data.update(payload)


class FakeCollection:
    def __init__(self, documents: dict):
        self.documents = documents

    def document(self, doc_id: str):
        if id not in self.documents:
            raise KeyError("No such document")
        return self.documents[id]


class FakeFirestoreClient:
    def __init__(self, jobs):
        self._jobs = {job_id: FakeDocRef(data) for job_id, data in jobs.items()}

    def collection(self, name: str):
        if name != "jobs":
            raise KeyError("Unexpected collection")
        return FakeCollection(self._jobs)


def test_process_statement_writes_parquet_in_batches(monkeypatch):
    # create a fake job with a SQL text that will produce 10 rows
    handle = "test-handle"
    job = {
        "sqlText": "SELECT 1",
        "statementHandle": handle,
        "status": "queued",
        "progress": 0,
    }
    fake_db = FakeFirestoreClient({handle: job})

    # monkeypatch the firestore client getter
    monkeypatch.setattr(worker_module, "_get_firestore_client", lambda: fake_db)

    # create a small orso DataFrame via import to mimic opteryx result
    from orso.dataframe import DataFrame

    rows = [{"c": i} for i in range(10)]
    df = DataFrame(dictionaries=rows)

    # Inject a fake opteryx module with an execute function returning our DataFrame
    import types
    fake_opteryx = types.SimpleNamespace(execute=lambda sql: df)
    sys.modules["opteryx"] = fake_opteryx

    # capture writes
    wrote = []

    def fake_write_table(table, path, *_args, **_kwargs):
        wrote.append(path)

    monkeypatch.setattr("pyarrow.parquet.write_table", fake_write_table, raising=False)

    # Call worker with a small batch size (4) to force batching
    worker_module.process_statement(handle, batch_size=4, bucket="opteryx_results")

    # We expect 3 output files: 4 + 4 + 2 rows -> 3 parts
    assert len(wrote) == 3
    # verify that we wrote to the expected bucket and path containing the handle
    for _idx, path in enumerate(wrote):
        assert path.startswith("gs://opteryx_results/test-handle/part_")

    # verify Firestore updates: first EXECUTING and final COMPLETED present
    doc_ref = fake_db.collection("jobs").document(handle)
    assert any(u.get("status") == "EXECUTING" for u in doc_ref.updates)
    assert any(u.get("status") == "COMPLETED" for u in doc_ref.updates)
