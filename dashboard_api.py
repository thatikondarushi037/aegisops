"""Bounded, read-only dashboard queries. No model inference or writes."""
from contextlib import contextmanager
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from dashboard_auth import browser_session
from database import get_db
from db_models import IncidentRecord, InvestigationJob, InvestigationRecord
from incident_schema import IncidentResponse
from investigation_schema import InvestigationHistory
from job_schema import InvestigationJobResponse

router = APIRouter(prefix="/dashboard/api", dependencies=[Depends(browser_session)])
JobStatus = Literal["pending", "running", "completed", "failed"]
Severity = Literal["critical", "warning", "normal"]


class IncidentRow(IncidentResponse):
    job_status: JobStatus | None


class IncidentPage(BaseModel):
    items: list[IncidentRow]
    total: int
    limit: int
    offset: int


class JobRow(InvestigationJobResponse):
    service: str


class JobPage(BaseModel):
    items: list[JobRow]
    total: int
    limit: int
    offset: int


class Overview(BaseModel):
    total_incidents: int
    open_incidents: int
    critical_incidents: int
    warning_incidents: int
    jobs: dict[JobStatus, int]
    refreshed_at: datetime


class IncidentDetail(BaseModel):
    incident: IncidentResponse
    job: InvestigationJobResponse | None


class HistoryPage(BaseModel):
    items: list[InvestigationHistory]
    total: int
    limit: int
    offset: int


@contextmanager
def controlled_read():
    try:
        yield
    except SQLAlchemyError:
        raise HTTPException(503, "Dashboard data is temporarily unavailable") from None


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    from datetime import timezone
    with controlled_read():
        counts = db.execute(select(
            func.count(),
            func.count().filter(IncidentRecord.status == "open"),
            func.count().filter(IncidentRecord.severity == "critical"),
            func.count().filter(IncidentRecord.severity == "warning"),
        ).select_from(IncidentRecord)).one()
        jobs = dict.fromkeys(["pending", "running", "completed", "failed"], 0)
        jobs.update(dict(db.execute(select(InvestigationJob.status, func.count())
                                   .group_by(InvestigationJob.status)).all()))
        return dict(zip(["total_incidents", "open_incidents", "critical_incidents", "warning_incidents"], counts),
                    jobs=jobs, refreshed_at=datetime.now(timezone.utc))


@router.get("/incidents", response_model=IncidentPage)
def incidents(service: str = Query("", max_length=100), severity: Severity | None = None,
              status: str | None = Query(None, max_length=20), limit: int = Query(20, ge=1, le=100),
              offset: int = Query(0, ge=0, le=1000000), db: Session = Depends(get_db)):
    filters = []
    if service:
        filters.append(IncidentRecord.service.icontains(service, autoescape=True))
    if severity:
        filters.append(IncidentRecord.severity == severity)
    if status:
        filters.append(IncidentRecord.status == status)
    with controlled_read():
        total = db.scalar(select(func.count()).select_from(IncidentRecord).where(*filters))
        rows = db.execute(select(IncidentRecord, InvestigationJob.status).outerjoin(
            InvestigationJob, IncidentRecord.id == InvestigationJob.incident_id
        ).where(*filters).order_by(IncidentRecord.created_at.desc(), IncidentRecord.id.desc())
          .limit(limit).offset(offset)).all()
        return {"items": [dict(IncidentResponse.model_validate(row).model_dump(), job_status=job) for row, job in rows],
                "total": total, "limit": limit, "offset": offset}


@router.get("/jobs", response_model=JobPage)
def jobs(status: JobStatus | None = None, limit: int = Query(20, ge=1, le=100),
         offset: int = Query(0, ge=0, le=1000000), db: Session = Depends(get_db)):
    filters = [InvestigationJob.status == status] if status else []
    with controlled_read():
        total = db.scalar(select(func.count()).select_from(InvestigationJob).where(*filters))
        rows = db.execute(select(InvestigationJob, IncidentRecord.service).join(
            IncidentRecord, IncidentRecord.id == InvestigationJob.incident_id
        ).where(*filters).order_by(InvestigationJob.updated_at.desc(), InvestigationJob.id.desc())
          .limit(limit).offset(offset)).all()
        return {"items": [dict(InvestigationJobResponse.model_validate(job).model_dump(), service=service)
                          for job, service in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
def detail(incident_id: int, db: Session = Depends(get_db)):
    with controlled_read():
        incident = db.get(IncidentRecord, incident_id)
        if incident is None:
            raise HTTPException(404, "Incident not found")
        job = db.scalar(select(InvestigationJob).where(InvestigationJob.incident_id == incident_id))
        return {"incident": incident, "job": job}


@router.get("/incidents/{incident_id}/history", response_model=HistoryPage)
def history(incident_id: int, limit: int = Query(5, ge=1, le=50),
            offset: int = Query(0, ge=0, le=1000000), db: Session = Depends(get_db)):
    with controlled_read():
        if db.get(IncidentRecord, incident_id) is None:
            raise HTTPException(404, "Incident not found")
        filters = InvestigationRecord.incident_id == incident_id
        total = db.scalar(select(func.count()).select_from(InvestigationRecord).where(filters))
        rows = db.scalars(select(InvestigationRecord).where(filters)
                          .order_by(InvestigationRecord.created_at.desc(), InvestigationRecord.id.desc())
                          .limit(limit).offset(offset)).all()
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
