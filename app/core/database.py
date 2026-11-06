"""MongoDB client lifecycle and connectivity checks."""

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import settings

_client: MongoClient | None = None


def connect_to_mongo() -> None:
    """Create the shared client and verify that MongoDB responds to ping."""
    global _client
    if _client is None:
        _client = MongoClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
        )
    _client.admin.command("ping")


def close_mongo_connection() -> None:
    """Close the shared MongoDB client, if one was created."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def check_mongo_connection() -> bool:
    """Return whether MongoDB is reachable without exposing driver errors."""
    try:
        connect_to_mongo()
    except PyMongoError:
        return False
    return True


def get_database():
    """Return the configured database after ensuring the server is reachable."""
    if _client is None:
        connect_to_mongo()
    return _client[settings.database_name]
