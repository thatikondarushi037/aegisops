
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

