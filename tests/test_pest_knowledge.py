from fastapi.testclient import TestClient

from app.main import app


def test_pest_knowledge_is_source_backed_and_not_a_detection_api():
    with TestClient(app) as client:
        result = client.get("/pest-knowledge")
        maize = client.get("/pest-knowledge?crop_name=maize")
        whitefly = client.get("/pest-knowledge/tomato-whitefly")
        unsupported = client.get("/pest-knowledge/unverified-pest")
    assert result.status_code == 200 and result.json()["total"] == 2
    assert maize.status_code == 200 and maize.json()["total"] == 1
    assert maize.json()["items"][0]["common_name"] == "Fall armyworm"
    assert whitefly.status_code == 200
    assert whitefly.json()["chemical_guidance_available"] is False
    assert whitefly.json()["sources"][0]["organization"] == "KALRO"
    assert unsupported.status_code == 404
