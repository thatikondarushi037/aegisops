
from typing import Literal

from pydantic import BaseModel, Field


class InvestigationResult(BaseModel):
    incident_id: int
    suspected_root_cause: str
    evidence: list[str]
    recommended_action: str
    confidence: Literal["low", "medium", "high"]
    requires_human_approval: bool = True
