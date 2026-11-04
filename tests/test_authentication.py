import pytest
from fastapi.testclient import TestClient
from app import app


@pytest.mark.parametrize("token", [None, "wrong", "wrong-unicode-token"])
@pytest.mark.parametrize("method,path", [
    ("GET", "/incidents"), ("POST", "/incidents"),
    ("GET", "/incidents/1"), ("PATCH", "/incidents/1"),
    ("DELETE", "/incidents/1"), ("POST", "/incidents/1/investigate"),
    ("GET", "/incidents/1/investigations"),
    ("GET", "/incidents/1/investigation-job"),
])
def test_reject_credentials_before_database(token, method, path):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with TestClient(app) as client:
        response = client.request(method, path, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "test-only" not in response.text


@pytest.mark.parametrize("method,path", [
    ("GET", "/incidents"), ("GET", "/incidents/1"),
    ("PATCH", "/incidents/1"), ("DELETE", "/incidents/1"),
    ("POST", "/incidents/1/investigate"),
    ("GET", "/incidents/1/investigations"),
    ("GET", "/incidents/1/investigation-job"),
])
def test_ingest_role_cannot_access_operator_routes(method, path):
    with TestClient(app) as client:
        assert client.request(method, path, headers={
            "Authorization": "Bearer test-only-ingest"
        }).status_code == 403


@pytest.mark.parametrize("value", ["", "test-only-operator"])
def test_configuration_fails_closed(monkeypatch, value):
    monkeypatch.setenv("AEGISOPS_N8N_TOKEN", value)
    with TestClient(app) as client:
        assert client.get("/incidents", headers={
            "Authorization": "Bearer test-only-operator"
        }).status_code == 503


def test_service_ingestion_and_duplicate(client, monkeypatch):
    import app as module
    monkeypatch.setattr(module, "investigate_incident", lambda *_: pytest.fail("Inference during ingestion"))
    headers = {"Authorization": "Bearer test-only-ingest"}
    payload = {"service": "n8n-retry", "error_rate": 15, "latency": 900}
    first = client.post("/incidents", json=payload, headers=headers)
    second = client.post("/incidents", json=payload, headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    job = client.get(f"/incidents/{first.json()['id']}/investigation-job").json()
    assert job["status"] == "pending" and job["attempts"] == 0
    assert client.post("/incidents", json={"service": "bad"}, headers=headers).status_code == 422
