import pyarrow as pa
import pyarrow.parquet as pq

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
        "statementHandle": "3ef2a90c-357f-4f89-96d5-69e832008839",
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

    def fake_write_table(_table_arg, path):
        writes.append(path)

    monkeypatch.setattr(pq, "write_table", fake_write_table)

    # Run the worker
    process_statement(job["statementHandle"], batch_size=100_000, bucket="opteryx_results")

    # We should have written a single part
    assert len(writes) == 1
    assert writes[0].endswith("part_0000.parquet")


def test_process_statement_multiple_batches(monkeypatch):
    # Create job
    job = {
        "statementHandle": "test-multi",
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
    def fake_write_table(_table_arg, path):
        writes.append(path)
    monkeypatch.setattr(pq, "write_table", fake_write_table)

    process_statement(job["statementHandle"], batch_size=10_000, bucket="opteryx_results")
    assert len(writes) == 3
    assert writes[0].endswith("part_0000.parquet")
    assert writes[1].endswith("part_0001.parquet")
    assert writes[2].endswith("part_0002.parquet")
