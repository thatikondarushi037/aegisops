
from typing import Literal

from pydantic import BaseModel, Field
from datetime import datetime


class InvestigationResult(BaseModel):
    incident_id: int
    suspected_root_cause: str
    evidence: list[str]
    recommended_action: str
    confidence: Literal["low", "medium", "high"]
    requires_human_approval: bool = True

from datetime import datetime

class InvestigationHistory(InvestigationResult):
    id: int
    created_at: datetime