
from fastapi import FastAPI, status
from fastapi import Depends

from database import get_db
from incident_schema import IncidentInput
from models import Incident

from sqlalchemy.orm import Session
from db_models import IncidentRecord


app = FastAPI(title="AegisOps API")


@app.get("/")
def home():
    return {"message": "AegisOps API is running"}



@app.post("/incidents", status_code=status.HTTP_201_CREATED)
def create_incident(
    incident: IncidentInput,
    db: Session = Depends(get_db)
):
    incident_model = Incident(
        service=incident.service,
        error_rate=incident.error_rate,
        latency=incident.latency
    )

    severity = incident_model.calculate_severity()
    
    record = IncidentRecord(
        service=incident.service,
        error_rate=incident.error_rate,
        latency=incident.latency,
        severity=severity
    )

    db.add(record)
    db.commit()
    db.refresh(record)



    return {
        "id": record.id,
        "service": record.service,
        "error_rate": record.error_rate,
        "latency": record.latency,
        "severity": record.severity,
        "created_at": record.created_at
    }
