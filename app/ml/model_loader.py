"""Lazy loading for the separately supplied TensorFlow/Keras model and labels."""

import json
from functools import lru_cache
from pathlib import Path

from app.core.config import BACKEND_ROOT, settings


class DiseaseModelUnavailable(RuntimeError):
    """Model assets or the TensorFlow runtime are not available."""


def _asset_path(configured_path: str) -> Path:
    """Resolve relative model paths from the backend root, not the shell cwd."""
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else BACKEND_ROOT / path


@lru_cache(maxsize=1)
def load_disease_model():
    model_path = settings.disease_model_path.strip()
    if not model_path or not _asset_path(model_path).is_file():
        raise DiseaseModelUnavailable("Disease detection model is not configured")
    try:
        from tensorflow.keras.models import load_model

        return load_model(str(_asset_path(model_path)), compile=False)
    except Exception as exc:
        raise DiseaseModelUnavailable("Disease detection model could not be loaded") from exc


@lru_cache(maxsize=1)
def load_class_labels() -> tuple[str, ...]:
    labels_path = settings.disease_labels_path.strip()
    if not labels_path or not _asset_path(labels_path).is_file():
        raise DiseaseModelUnavailable("Disease detection labels are not configured")
    try:
        data = json.loads(_asset_path(labels_path).read_text(encoding="utf-8"))
        labels = data.get("classes") if isinstance(data, dict) else data
        if not isinstance(labels, list) or not labels or any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("Invalid class labels")
        return tuple(label.strip() for label in labels)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise DiseaseModelUnavailable("Disease detection labels could not be loaded") from exc
