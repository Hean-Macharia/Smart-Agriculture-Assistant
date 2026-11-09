"""Model inference, intentionally separate from HTTP handling."""

import numpy as np

from app.ml.image_preprocessing import preprocess_image
from app.ml.model_loader import DiseaseModelUnavailable, load_class_labels, load_disease_model


def predict_disease(image_bytes: bytes) -> tuple[str, float]:
    """Return the best configured class and confidence, or fail if no model exists."""
    batch = preprocess_image(image_bytes)
    model = load_disease_model()
    labels = load_class_labels()
    try:
        output = np.asarray(model.predict(batch, verbose=0), dtype=np.float64)
    except Exception as exc:
        raise DiseaseModelUnavailable("Disease detection inference failed") from exc
    if output.ndim != 2 or output.shape[0] != 1 or output.shape[1] != len(labels):
        raise DiseaseModelUnavailable("Model output does not match the configured disease labels")
    scores = output[0]
    if not np.all(np.isfinite(scores)):
        raise DiseaseModelUnavailable("Model returned invalid confidence values")
    if np.any(scores < 0) or np.any(scores > 1) or not np.isclose(scores.sum(), 1.0, atol=1e-3):
        shifted = scores - np.max(scores)
        exp_scores = np.exp(shifted)
        scores = exp_scores / exp_scores.sum()
    best = int(np.argmax(scores))
    return labels[best], float(scores[best])
