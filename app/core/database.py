"""MongoDB client lifecycle and connectivity checks."""

import logging
from threading import Lock

from pymongo import MongoClient
from pymongo.errors import (
    ConfigurationError,
    ConnectionFailure,
    NetworkTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)

from app.core.config import settings

_client: MongoClient | None = None
_client_lock = Lock()
logger = logging.getLogger(__name__)


def _get_client() -> MongoClient:
    """Return the single process-wide client, creating it safely under concurrency."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MongoClient(
                    settings.mongodb_uri,
                    serverSelectionTimeoutMS=settings.mongodb_server_selection_timeout_ms,
                    # MongoDB stores BSON datetimes in UTC; keep them timezone-aware
                    # when reading documents back for consistent API serialization.
                    tz_aware=True,
                )
    return _client


def connect_to_mongo() -> None:
    """Create the shared client and verify that MongoDB responds to ping."""
    _get_client().admin.command("ping")


def close_mongo_connection() -> None:
    """Close the shared MongoDB client, if one was created."""
    global _client
    with _client_lock:
        client, _client = _client, None
    if client is not None:
        client.close()


def _log_safe_connection_failure(exc: PyMongoError) -> None:
    if isinstance(exc, ServerSelectionTimeoutError):
        category = "server_selection_timeout"
    elif isinstance(exc, NetworkTimeout):
        category = "network_timeout"
    elif isinstance(exc, ConfigurationError):
        category = "client_configuration"
    elif isinstance(exc, OperationFailure) and exc.code in {13, 18, 8000}:
        category = "authentication_or_authorization"
    elif isinstance(exc, ConnectionFailure):
        category = "connection_or_tls_failure"
    else:
        category = "driver_error"

    nested_types = []
    errors = getattr(exc, "errors", None)
    descriptions = errors.values() if isinstance(errors, dict) else errors if isinstance(errors, (list, tuple)) else ()
    for description in descriptions:
        nested = getattr(description, "error", None)
        if nested is not None:
            nested_types.append(type(nested).__name__)
    logger.warning(
        "MongoDB readiness ping failed: category=%s type=%s code=%s code_name=%s nested_types=%s",
        category,
        type(exc).__name__,
        getattr(exc, "code", None),
        getattr(exc, "code_name", None),
        ",".join(sorted(set(nested_types))) or "none",
    )


def check_mongo_connection() -> bool:
    """Return whether MongoDB is reachable without exposing driver errors."""
    try:
        connect_to_mongo()
    except PyMongoError as exc:
        _log_safe_connection_failure(exc)
        return False
    return True


def get_database():
    """Return the configured database after ensuring the server is reachable."""
    if _client is None:
        connect_to_mongo()
    return _get_client()[settings.database_name]
