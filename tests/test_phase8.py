from datetime import datetime, timezone
from io import BytesIO

import cv2
import numpy as np
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_disease_report_repository
from app.main import app
from app.ml.disease_model import predict_disease
from app.ml.model_loader import DiseaseModelUnavailable
from app.models.user import UserRole
from app.schemas.user import UserPublic
from app.services import disease_service

FARMER_ID = "64b000000000000000000001"
BUYER_ID = "64b000000000000000000003"


def make_user(user_id=FARMER_ID, role=UserRole.FARMER):
    now = datetime.now(timezone.utc)
    return UserPublic(id=user_id, full_name="Test Farmer", email="farmer@example.test", phone="+254700000000", role=role, is_active=True, created_at=now, updated_at=now)


def png_bytes():
    image = np.zeros((64, 80, 3), dtype=np.uint8)
    image[:, :, 1] = 180
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


class MemoryDiseaseReports:
    def __init__(self):
        self.items = []

    def create(self, values):
        item = {**values, "id": str(ObjectId()), "created_at": datetime.now(timezone.utc)}
        self.items.append(item)
        return item

    def list_for_farmer(self, farmer_id, *, skip, limit):
        items = [item for item in self.items if item["farmer_id"] == farmer_id]
        return items[skip:skip + limit], len(items)


@pytest.fixture
def disease_client():
    current = {"user": make_user()}
    repository = MemoryDiseaseReports()
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[get_disease_report_repository] = lambda: repository
    with TestClient(app) as client:
        yield client, current, repository
    app.dependency_overrides.clear()


def test_image_preprocessing_decodes_resizes_normalizes_and_batches():
    from app.ml.image_preprocessing import preprocess_image

    batch = preprocess_image(png_bytes())
    assert batch.shape == (1, 224, 224, 3)
    assert batch.dtype == np.float32
    assert float(batch.min()) >= 0 and float(batch.max()) <= 1


def test_image_preprocessing_rejects_corrupt_image():
    from app.ml.image_preprocessing import InvalidDiseaseImage, preprocess_image

    with pytest.raises(InvalidDiseaseImage):
        preprocess_image(b"not an image")


def test_image_preprocessing_rejects_excessive_pixel_dimensions():
    from PIL import Image
    from app.ml.image_preprocessing import InvalidDiseaseImage, preprocess_image

    buffer = BytesIO()
    Image.new("RGB", (5001, 5000)).save(buffer, format="PNG", optimize=True)
    with pytest.raises(InvalidDiseaseImage, match="dimensions"):
        preprocess_image(buffer.getvalue())


def test_prediction_endpoint_records_history_and_disclaimer(disease_client, monkeypatch):
    client, _, repository = disease_client
    monkeypatch.setattr(disease_service, "predict_disease", lambda _: ("Maize___Healthy", 0.91))
    response = client.post("/disease-detection/predict", files={"image": ("leaf.png", png_bytes(), "image/png")})
    assert response.status_code == 201
    result = response.json()
    assert result["predicted_label"] == "Maize___Healthy"
    assert result["confidence"] == pytest.approx(0.91)
    assert "not a guaranteed diagnosis" in result["disclaimer"]
    assert len(repository.items) == 1
    assert repository.items[0]["image_sha256"]
    history = client.get("/disease-detection/mine")
    assert history.status_code == 200 and history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == result["id"]


def test_prediction_endpoint_rejects_wrong_role(disease_client):
    client, current, _ = disease_client
    current["user"] = make_user(BUYER_ID, UserRole.BUYER)
    response = client.post("/disease-detection/predict", files={"image": ("leaf.png", png_bytes(), "image/png")})
    assert response.status_code == 403


def test_prediction_endpoint_rejects_invalid_mime_and_corrupt_content(disease_client):
    client, _, _ = disease_client
    wrong_type = client.post("/disease-detection/predict", files={"image": ("leaf.txt", b"text", "text/plain")})
    assert wrong_type.status_code == 415
    corrupt = client.post("/disease-detection/predict", files={"image": ("leaf.png", b"not a png", "image/png")})
    assert corrupt.status_code == 422


def test_prediction_endpoint_reports_unavailable_model_without_fabricating_prediction(disease_client, monkeypatch):
    client, _, repository = disease_client
    monkeypatch.setattr(disease_service, "predict_disease", lambda _: (_ for _ in ()).throw(DiseaseModelUnavailable("not configured")))
    response = client.post("/disease-detection/predict", files={"image": ("leaf.png", png_bytes(), "image/png")})
    assert response.status_code == 503
    assert "model and label map" in response.json()["detail"]
    assert repository.items == []


def test_prediction_endpoint_enforces_upload_size(disease_client, monkeypatch):
    import app.routes.disease_detection as route

    client, _, _ = disease_client
    monkeypatch.setattr(route.settings, "disease_image_max_bytes", 8)
    response = client.post("/disease-detection/predict", files={"image": ("leaf.png", b"x" * 9, "image/png")})
    assert response.status_code == 413


def test_model_inference_selects_label_and_normalizes_logits(monkeypatch):
    import app.ml.disease_model as inference

    class FakeModel:
        def predict(self, batch, verbose=0):
            assert batch.shape[0] == 1 and verbose == 0
            return np.array([[1.0, 3.0]])

    monkeypatch.setattr(inference, "preprocess_image", lambda _: np.zeros((1, 224, 224, 3), dtype=np.float32))
    monkeypatch.setattr(inference, "load_disease_model", lambda: FakeModel())
    monkeypatch.setattr(inference, "load_class_labels", lambda: ("Maize___Healthy", "Maize___Common_Rust"))
    label, confidence = predict_disease(b"image bytes")
    assert label == "Maize___Common_Rust"
    assert confidence == pytest.approx(0.880797, rel=1e-5)


def test_model_inference_rejects_output_label_mismatch(monkeypatch):
    import app.ml.disease_model as inference

    class FakeModel:
        def predict(self, batch, verbose=0):
            return np.array([[0.5, 0.5]])

    monkeypatch.setattr(inference, "preprocess_image", lambda _: np.zeros((1, 224, 224, 3), dtype=np.float32))
    monkeypatch.setattr(inference, "load_disease_model", lambda: FakeModel())
    monkeypatch.setattr(inference, "load_class_labels", lambda: ("one label",))
    with pytest.raises(DiseaseModelUnavailable):
        predict_disease(b"image bytes")
