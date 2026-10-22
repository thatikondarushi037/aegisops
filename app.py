
from fastapi import HTTPException

from fastapi import FastAPI, status
from fastapi import Depends

from fastapi import Response

from database import get_db
from incident_schema import IncidentInput
from incident_schema import IncidentInput, IncidentResponse, IncidentUpdate
from sqlalchemy.exc import SQLAlchemyError

from models import Incident


from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


from sqlalchemy.orm import Session
from db_models import IncidentRecord


app = FastAPI(title="AegisOps API")


@app.get("/")
def home():
    return {"message": "AegisOps API is running"}



@app.post("/incidents", status_code=status.HTTP_201_CREATED, response_model=IncidentResponse)

def create_incident(
    incident: IncidentInput,
    response: Response,
    db: Session = Depends(get_db),
):
    incident_model = Incident(
        service=incident.service,
        error_rate=incident.error_rate,
        latency=incident.latency
    )

    severity = incident_model.calculate_severity()
    
    
    existing_incident = find_open_incident(db, incident.service)
    if existing_incident is not None:
        response.status_code = status.HTTP_200_OK
        return existing_incident
    
    record = IncidentRecord(
        service=incident.service,
        error_rate=incident.error_rate,
        latency=incident.latency,
        severity=severity
    )
    
    try:

        db.add(record)
        db.commit()
        db.refresh(record)
        return record
        
    except IntegrityError as error:
        db.rollback()

        constraint_name = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None
        )
        
        if constraint_name != "uq_incidents_open_service":
            raise HTTPException(
                status_code=500,
                detail="Database operation failed"
            ) from error

        existing = find_open_incident(db, incident.service)

        if existing is None:
            raise HTTPException(
                status_code=503,
                detail="Incident conflict could not be resolved"
            )

        response.status_code = status.HTTP_200_OK
        return existing

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Database operation failed"
        )



    return {
        "id": record.id,
        "service": record.service,
        "error_rate": record.error_rate,
        "latency": record.latency,
        "severity": record.severity,
        "created_at": record.created_at,
        "status":record.status
    }



@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db)
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    return incident


@app.get("/incidents", response_model=list[IncidentResponse])
def get_incidents(
    db: Session = Depends(get_db)
):
    statement = select(IncidentRecord)

    incidents = db.scalars(statement).all()

    return incidents



@app.patch("/incidents/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    updates: IncidentUpdate,
    db: Session = Depends(get_db)
):
    record = db.get(IncidentRecord, incident_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    update_data = updates.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null"
            )

        setattr(record, field, value)

    incident_model = Incident(
        service=record.service,
        error_rate=record.error_rate,
        latency=record.latency
    )

    record.severity = incident_model.calculate_severity()

    db.commit()
    db.refresh(record)

    return record




@app.delete(
    "/incidents/{incident_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_incident(
    incident_id: int,
    db: Session = Depends(get_db)
):
    record = db.get(IncidentRecord, incident_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    db.delete(record)
    db.commit()
    
def find_open_incident(
    db:Session,
    service: str
):
    return(
        db.query(IncidentRecord)
        .filter(
            IncidentRecord.service == service,
            IncidentRecord.status == "open"
        )
        .order_by(IncidentRecord.id.desc())
        .first()
    )
