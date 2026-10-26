
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy import ForeignKey, Text, JSON, Boolean

from database import Base


class IncidentRecord(Base):
    __tablename__ = "incidents"

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
