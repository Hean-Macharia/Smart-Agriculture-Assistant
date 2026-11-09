"""Disease inference workflow and private prediction history."""

import hashlib
from pathlib import Path

from app.ml.disease_model import predict_disease
from app.repositories.disease_report_repository import DiseaseReportRepository

DISCLAIMER = "AI model output is a preliminary screening result, not a guaranteed diagnosis. Ask an agricultural officer to assess uncertain or serious cases."


def create_disease_report(repository: DiseaseReportRepository, *, farmer_id: str, filename: str, content_type: str, image_bytes: bytes):
    label, confidence = predict_disease(image_bytes)
    safe_filename = Path(filename or "crop-image").name[:160]
    return repository.create({
        "farmer_id": farmer_id,
        "filename": safe_filename,
        "content_type": content_type,
        "file_size_bytes": len(image_bytes),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "predicted_label": label,
        "confidence": confidence,
        "disclaimer": DISCLAIMER,
    })
