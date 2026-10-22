
def test_create_incident(client):
    response = client.post(
        "/incidents",
        json={
            "service": "isolation-check-service",
            "error_rate": 18,
            "latency": 300
        }
    )

    assert response.status_code == 201

    data = response.json()

    assert data["service"] == "isolation-check-service"
    assert data["severity"] == "critical"
    assert isinstance(data["id"], int)




def test_previous_incident_does_not_persist(client):
    response = client.get("/incidents")

    assert response.status_code == 200

    incidents = response.json()

    assert not any(
        incident["service"] == "isolation-check-service"
        for incident in incidents
    )

def test_duplicate_incident_reuses_existing(client):
    payload = {
        "service": "duplicate-test-service",
        "error_rate": 12.0,
        "latency": 1100
    }

    first = client.post("/incidents", json=payload)
    second = client.post("/incidents", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200

    assert first.json()["id"] == second.json()["id"]

