"""Shared validated generation and persistence, with no implicit commit."""

from db_models import InvestigationRecord
from investigation_schema import InvestigationResult
from llm_investigator import investigate_incident, validate_investigation


def incident_snapshot(record):
    return {key: getattr(record, key) for key in ("id", "service", "error_rate", "latency", "severity")}


def validated_result(result, incident):
    # Revalidate even a model instance: callers may have mutated it since its
    # original construction (Pydantic normally trusts existing instances).
    if isinstance(result, InvestigationResult):
        result = result.model_dump()
    result = InvestigationResult.model_validate(result)
    result = validate_investigation(result, incident)
    # Metrics alone cannot establish a root cause, even if a model claims high
    # confidence. Evidence and approval are checked again at persistence.
    result.confidence = "low"
    return result


def generate_investigation(incident, investigator=None):
    return validated_result((investigator or investigate_incident)(incident), incident)


def save_investigation(db, result, incident):
    result = validated_result(result, incident)
    record = InvestigationRecord(**result.model_dump())
    db.add(record)
    db.flush()
    return record
