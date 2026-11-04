from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class InvestigationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: int
    trigger: Literal["automatic_initial"]
    status: Literal["pending", "running", "completed", "failed"]
    attempts: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    error_category: str | None
    error_message: str | None
    investigation_id: int | None
