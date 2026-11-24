from concurrent.futures import ThreadPoolExecutor

from pymongo.errors import ServerSelectionTimeoutError

from app.core import database


def test_concurrent_first_access_creates_one_shared_client(monkeypatch):
    instances = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            instances.append(self)
            self.close_count = 0

        def close(self):
            self.close_count += 1

    monkeypatch.setattr(database, "MongoClient", FakeClient)
    monkeypatch.setattr(database, "_client", None)
    with ThreadPoolExecutor(max_workers=12) as executor:
        clients = list(executor.map(lambda _: database._get_client(), range(48)))
    assert len(instances) == 1
    assert all(client is instances[0] for client in clients)
    database.close_mongo_connection()
    assert instances[0].close_count == 1


def test_connection_failure_log_omits_driver_message_and_uri(monkeypatch, caplog):
    secret_uri = "mongodb+srv://user:secret@example.invalid/db"

    def fail_ping():
        raise ServerSelectionTimeoutError(secret_uri)

    monkeypatch.setattr(database, "connect_to_mongo", fail_ping)
    assert database.check_mongo_connection() is False
    assert "server_selection_timeout" in caplog.text
    assert secret_uri not in caplog.text
    assert "secret" not in caplog.text
