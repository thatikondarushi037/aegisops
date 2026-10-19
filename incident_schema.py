
from pydantic import BaseModel, Field


class IncidentInput(BaseModel):
    service: str = Field(min_length=1)
    error_rate: float = Field(ge=0, le=100)
    latency: int = Field(ge=0)
    
