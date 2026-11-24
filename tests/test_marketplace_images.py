from io import BytesIO
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from PIL import Image

from app.core import config
from app.core.dependencies import get_current_user
from app.main import app
from app.schemas.user import UserPublic


def test_validated_product_image_upload_is_dev_only_and_normalized(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    user = UserPublic(id="64b000000000000000000001", full_name="Farmer", email="farmer@example.test", phone="+254712345678", role="FARMER", is_active=True, created_at=now, updated_at=now)
    monkeypatch.setattr(config.settings, "app_env", "test")
    monkeypatch.setattr("app.routes.marketplace.BACKEND_ROOT", tmp_path)
    monkeypatch.setattr("app.main.product_images", tmp_path / "uploads" / "product_images")
    app.dependency_overrides[get_current_user] = lambda: user
    image = Image.new("RGB", (120, 80), (30, 120, 40))
    source = BytesIO()
    image.save(source, format="PNG")
    try:
        with TestClient(app) as client:
            response = client.post("/marketplace/products/images", files={"image": ("tomato.png", source.getvalue(), "image/png")})
            assert response.status_code == 201
            data = response.json()
            assert data["content_type"] == "image/webp"
            assert data["width"] == 120 and data["height"] == 80
            asset = tmp_path / "uploads" / "product_images" / data["url"].rsplit("/", 1)[-1]
            assert asset.is_file()
            served = client.get(data["url"])
            assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
            assert client.post("/marketplace/products/images", files={"image": ("bad.txt", b"not image", "text/plain")}).status_code == 415
            assert client.get("/media/products/../secret.webp").status_code in {404, 422}
    finally:
        app.dependency_overrides.clear()
