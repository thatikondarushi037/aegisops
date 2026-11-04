
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import ForeignKey, Text, JSON, Boolean, CheckConstraint, UniqueConstraint

from database import Base


class IncidentRecord(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index(
            "uq_incidents_open_service",
            "service",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )

    service: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    error_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    latency: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )
    
    
    
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="open"
    )


    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )



class InvestigationRecord(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    incident_id: Mapped[int] = mapped_column(
        ForeignKey("incidents.id"),
        nullable=False
    )

    suspected_root_cause: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    evidence: Mapped[list] = mapped_column(
        JSON, nullable=False
    )

    recommended_action: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    requires_human_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class InvestigationJob(Base):
    __tablename__ = "investigation_jobs"
    __table_args__ = (
        UniqueConstraint("incident_id", "trigger", name="uq_investigation_jobs_incident_trigger"),
        UniqueConstraint("investigation_id", name="uq_investigation_jobs_result"),
        CheckConstraint("trigger = 'automatic_initial'", name="ck_investigation_jobs_trigger"),
        CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_investigation_jobs_status"),
        CheckConstraint("attempts >= 0 AND max_attempts BETWEEN 1 AND 10 AND attempts <= max_attempts", name="ck_investigation_jobs_attempts"),
        CheckConstraint("(status = 'completed') = (investigation_id IS NOT NULL)", name="ck_investigation_jobs_result"),
        CheckConstraint("(status = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL)", name="ck_investigation_jobs_claim"),
        Index("ix_investigation_jobs_ready", "status", "next_attempt_at", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Preserve deletion of incidents with no investigation history. Existing
    # investigations still retain their original restrictive incident FK.
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, server_default="automatic_initial")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[str | None] = mapped_column(String(36))
    error_category: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(String(200))
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"))
