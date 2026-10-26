from investigation_schema import InvestigationResult


result = InvestigationResult(
    incident_id=54,
    suspected_root_cause="unknown -more evidence required",
    evidence=["Elevated error rate",
                "Elevated latency"],
    recommended_action="Collect application logs",
    confidence="low")


print(result.model_dump_json(indent=2))