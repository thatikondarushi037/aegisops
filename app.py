
from fastapi import HTTPException

from fastapi import FastAPI, status
from fastapi import Depends
from sqlalchemy import select

from fastapi import Response
from llm_investigator  import investigate_incident
from investigation_schema import InvestigationResult, InvestigationHistory
from database import get_db
from incident_schema import IncidentInput
from incident_schema import IncidentInput, IncidentResponse, IncidentUpdate
from sqlalchemy.exc import SQLAlchemyError

from models import Incident


from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


from sqlalchemy.orm import Session
from db_models import IncidentRecord, InvestigationRecord, InvestigationJob
from investigation_service import generate_investigation, incident_snapshot, save_investigation
from job_schema import InvestigationJobResponse
from settings import WorkerSettings
import requests


from authentication import require_ingest, require_operator

app = FastAPI(title="AegisOps API", version="0.18.0")

# The browser surface is read-only and uses a separate session boundary.
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dashboard_auth import router as dashboard_auth_router
from dashboard_api import router as dashboard_api_router
from assistant_api import router as assistant_router

frontend_directory = Path(__file__).resolve().parent / "frontend"
app.include_router(dashboard_auth_router)
app.include_router(dashboard_api_router)
app.include_router(assistant_router)
app.mount("/dashboard/assets", StaticFiles(directory=frontend_directory), name="dashboard-assets")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(frontend_directory / "index.html")


@app.middleware("http")
async def dashboard_headers(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/dashboard"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'; object-src 'none'"
        )
    return response


@app.get("/")
def home():
    return {"message": "AegisOps API is running"}



@app.post("/incidents", dependencies=[Depends(require_ingest)], status_code=status.HTTP_201_CREATED, response_model=IncidentResponse)

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
        db.flush()
        db.add(InvestigationJob(
            incident_id=record.id,
            max_attempts=WorkerSettings.from_env().max_attempts,
        ))
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



@app.get("/incidents/{incident_id}", dependencies=[Depends(require_operator)], response_model=IncidentResponse)
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


@app.get("/incidents", dependencies=[Depends(require_operator)], response_model=list[IncidentResponse])
def get_incidents(
    db: Session = Depends(get_db)
):
    statement = select(IncidentRecord)

    incidents = db.scalars(statement).all()

    return incidents



@app.patch("/incidents/{incident_id}", dependencies=[Depends(require_operator)], response_model=IncidentResponse)
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
    dependencies=[Depends(require_operator)],
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


@app.post(
    "/incidents/{incident_id}/investigate",
    dependencies=[Depends(require_operator)],
    response_model=InvestigationResult
)
def investigate_existing_incident(
    incident_id: int,
    db: Session = Depends(get_db)
):
    record = db.get(IncidentRecord, incident_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    incident_data = incident_snapshot(record)
    # End the read transaction before slow model work. The shared service
    # checks identity, metrics evidence, and mandatory human approval.
    db.rollback()
    try:
        result = generate_investigation(incident_data, investigator=investigate_incident)
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="Investigation model timed out") from None
    except (requests.RequestException, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=502, detail="Investigation model failed validation or is unavailable") from None

    try:
        save_investigation(db, result, incident_data)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to save investigation"
        )

    return result


@app.get(
    "/incidents/{incident_id}/investigations",
    dependencies=[Depends(require_operator)],
    response_model=list[InvestigationHistory]
)
def get_investigation_history(
    incident_id: int,
    db: Session = Depends(get_db)
):
    incident = db.get(IncidentRecord, incident_id)

    if incident is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found"
        )

    statement = (
        select(InvestigationRecord)
        .where(InvestigationRecord.incident_id == incident_id)
        .order_by(InvestigationRecord.created_at.desc())
    )

    return db.scalars(statement).all()


@app.get(
    "/incidents/{incident_id}/investigation-job",
    dependencies=[Depends(require_operator)],
    response_model=InvestigationJobResponse,
)
def get_automatic_investigation_job(incident_id: int, db: Session = Depends(get_db)):
    if db.get(IncidentRecord, incident_id) is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    job = db.scalar(select(InvestigationJob).where(
        InvestigationJob.incident_id == incident_id,
        InvestigationJob.trigger == "automatic_initial",
    ))
    if job is None:
        raise HTTPException(status_code=404, detail="Automatic investigation job not found")
    return job
