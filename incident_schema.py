
from pydantic import BaseModel, Field


class IncidentInput(BaseModel):
    service: str = Field(min_length=1)
    error_rate: float = Field(ge=0, le=100)
    latency: int = Field(ge=0)
    
    

from datetime import datetime
from pydantic import ConfigDict


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service: str
    error_rate: float
    latency: int
    severity: str
    created_at: datetime



class IncidentUpdate(BaseModel):
    service: str | None = Field(default=None, min_length=1)
    error_rate: float | None = Field(default=None, ge=0, le=100)
    latency : int | None = Field(default=None, ge=0)