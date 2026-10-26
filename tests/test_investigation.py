import pytest
import app as app_module
from investigation_schema import InvestigationResult
from investigation_schema import InvestigationResult
from llm_investigator import validate_investigation

def make_result(incident_id=54, approval=True):
    return InvestigationResult(
        incident_id=incident_id,
        suspected_root_cause="unknown",
        evidence=[],
        recommended_action="Collect application logs",
        confidence="low",
        requires_human_approval=approval
    )
def test_validate_investigation():
    incident = {"id": 54,
                    "service": "payment-service",
                    "error_rate": 15.0,
                    "latency": 1200}
    result = validate_investigation(make_result(), incident)
    
    assert result.incident_id == 54
    assert result.requires_human_approval is True
    assert len(result.evidence) == 2
    
def test_incorrect_incident_id():
    incident = {"id": 55,
                    "service": "payment-service",
                    "error_rate": 15.0,
                    "latency": 1200}
    with pytest.raises(ValueError, match="Incorrect incident ID"):
        validate_investigation(make_result(incident_id=999), incident)
        
def test_investigation_history_unknown_incident(client):
    # Choose an ID that does not exist in the isolated test database.
    response = client.get(
        "/incidents/999999999/investigations"
    )

    # An unknown incident must not have accessible history.
    assert response.status_code == 404
    assert response.json()["detail"] == "Incident not found"
def test_investigation_is_saved(client, monkeypatch):
    # 1. Create a real incident in the isolated test database.
    create_response = client.post(
        "/incidents",
        json={
            "service": "investigation-test-service",
            "error_rate": 15.0,
            "latency": 1200
        }
    )

    assert create_response.status_code == 201
    incident_id = create_response.json()["id"]

    # 2. Replace the real Ollama call with a predictable result.
    def fake_investigator(incident):
        return InvestigationResult(
            incident_id=incident["id"],
            suspected_root_cause="Unknown",
            evidence=[
                "Error rate exceeded the critical threshold"
            ],
            recommended_action="Inspect service logs",
            confidence="low",
            requires_human_approval=True
        )

    monkeypatch.setattr(
        app_module,
        "investigate_incident",
        fake_investigator
    )

    # 3. Generate and persist an investigation.
    response = client.post(
        f"/incidents/{incident_id}/investigate"
    )

    assert response.status_code == 200

    # 4. Retrieve the history from the database.
    history_response = client.get(
        f"/incidents/{incident_id}/investigations"
    )

    assert history_response.status_code == 200

    history = history_response.json()

    assert len(history) == 1
    assert history[0]["incident_id"] == incident_id
    assert history[0]["suspected_root_cause"] == "Unknown"
    assert history[0]["recommended_action"] == "Inspect service logs"
    assert history[0]["requires_human_approval"] is True