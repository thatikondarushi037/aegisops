"""Five typed, session-authorized, read-only assistant capabilities."""
import os
import re
import time
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

import dashboard_auth
from db_models import IncidentRecord, InvestigationJob, InvestigationRecord
from rag_retriever import retrieve_runbooks
from settings import OLLAMA_BASE_URL


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListIncidents(Arguments):
    severity: Literal["critical", "warning", "normal"] | None = None
    status: Literal["open", "closed", "resolved", "superseded"] | None = None
    job_status: Literal["pending", "running", "completed", "failed"] | None = None
    limit: int = Field(default=5, ge=1, le=5)


class IncidentID(Arguments):
    incident_id: int = Field(ge=1, le=2147483647)


class GetInvestigations(IncidentID):
    limit: int = Field(default=2, ge=1, le=2)


class SearchRunbooks(Arguments):
    query: str = Field(min_length=1, max_length=240)
    limit: int = Field(default=2, ge=1, le=2)


TOOL_SCHEMAS = {
    "list_incidents": ListIncidents,
    "get_incident": IncidentID,
    "get_investigations": GetInvestigations,
    "get_investigation_job": IncidentID,
    "search_runbooks": SearchRunbooks,
}


def safe_text(value, limit=1200):
    text = str(value)
    for key, secret in os.environ.items():
        if secret and len(secret) >= 4 and any(word in key.upper() for word in ("TOKEN", "PASSWORD", "SECRET", "_KEY")):
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text if len(text) <= limit else text[:limit] + " [truncated]"


def require_active(session):
    with dashboard_auth.lock:
        valid = session.expires > time.monotonic() and any(value is session for value in dashboard_auth.sessions.values())
    if not valid:
        raise HTTPException(401, "Dashboard login required")


def require_local_ollama():
    endpoint = urlsplit(OLLAMA_BASE_URL)
    if endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {
        "localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"
    }:
        raise ValueError("Assistant inference requires a configured local model endpoint")


def incident_data(record):
    return dict(id=record.id, service=safe_text(record.service, 100), error_rate=record.error_rate,
                latency=record.latency, severity=record.severity, status=record.status,
                created_at=record.created_at.isoformat())


class ReadOnlyTools:
    MAX_CALLS = 4

    def __init__(self, db, session, deadline):
        self.db, self.session, self.deadline = db, session, deadline
        self.calls = []

    def call(self, name, arguments):
        require_active(self.session)
        if name not in TOOL_SCHEMAS:
            raise ValueError("Tool is not allowed")
        args = TOOL_SCHEMAS[name].model_validate(arguments)
        if len(self.calls) >= self.MAX_CALLS or time.monotonic() >= self.deadline:
            raise ValueError("Assistant tool budget exhausted")
        self.calls.append(name)
        # The dispatcher is explicit: no eval, arbitrary getattr, SQL text, URLs or paths.
        if name == "list_incidents":
            filters = []
            if args.severity:
                filters.append(IncidentRecord.severity == args.severity)
            if args.status:
                filters.append(IncidentRecord.status == args.status)
            if args.job_status:
                filters.append(InvestigationJob.status == args.job_status)
            query = select(IncidentRecord, InvestigationJob).outerjoin(
                InvestigationJob, InvestigationJob.incident_id == IncidentRecord.id).where(*filters)
            total = self.db.scalar(select(func.count()).select_from(query.subquery()))
            rows = self.db.execute(query.order_by(IncidentRecord.created_at.desc(), IncidentRecord.id.desc()).limit(args.limit)).all()
            return {"total": total, "items": [dict(incident_data(row), job_status=job.status if job else None,
                    attempts=job.attempts if job else None) for row, job in rows]}
        if name == "get_incident":
            record = self.db.get(IncidentRecord, args.incident_id)
            return incident_data(record) if record else None
        if name == "get_investigations":
            rows = self.db.scalars(select(InvestigationRecord).where(InvestigationRecord.incident_id == args.incident_id)
                       .order_by(InvestigationRecord.created_at.desc(), InvestigationRecord.id.desc()).limit(args.limit)).all()
            return [dict(id=row.id, incident_id=row.incident_id, evidence=[safe_text(x, 250) for x in (row.evidence[:6] if isinstance(row.evidence, list) else [])],
                         suspected_root_cause=safe_text(row.suspected_root_cause), recommended_action=safe_text(row.recommended_action),
                         confidence=row.confidence, requires_human_approval=row.requires_human_approval) for row in rows]
        if name == "get_investigation_job":
            row = self.db.scalar(select(InvestigationJob).where(InvestigationJob.incident_id == args.incident_id))
            return None if row is None else dict(id=row.id, status=row.status, attempts=row.attempts,
                       max_attempts=row.max_attempts, investigation_id=row.investigation_id,
                       error_category=safe_text(row.error_category, 80) if row.error_category else None)
        # End any database transaction before network-based runbook embeddings.
        self.db.rollback()
        require_local_ollama()
        matches = retrieve_runbooks(args.query, top_k=args.limit,
                                   deadline=min(self.deadline, time.monotonic() + 15), max_chunks=24)
        return [dict(source=safe_text(re.split(r"[/\\]", row["source"])[-1], 100),
                     text=safe_text(row["text"], 1600)) for row in matches]
