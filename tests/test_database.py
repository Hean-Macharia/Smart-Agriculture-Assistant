from app.core import database


def test_mongodb_client_uses_timezone_aware_utc_datetimes(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, uri, **kwargs):
            captured["uri"] = uri
            captured.update(kwargs)
            self.admin = self

        def command(self, name):
            assert name == "ping"
            return {"ok": 1}

        def close(self):
            pass

    monkeypatch.setattr(database, "_client", None)
    monkeypatch.setattr(database, "MongoClient", FakeClient)
    try:
        database.connect_to_mongo()
        assert captured["tz_aware"] is True
        assert captured["serverSelectionTimeoutMS"] > 0
    finally:
        database.close_mongo_connection()
