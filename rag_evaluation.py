
import json
from pathlib import Path

from llm_investigator import investigate_incident


# Use identical incident data for both experiments.
TEST_INCIDENT = {
    "id": 54,
    "service": "payment-service",
    "error_rate": 15.0,
    "latency": 1200,
    "severity": "critical"
}


def run_evaluation():
    print("Running LLM-only investigation...")
    llm_result = investigate_incident(
        TEST_INCIDENT,
        use_rag=False
    )

    print("\nRunning RAG-assisted investigation...")
    rag_result = investigate_incident(
        TEST_INCIDENT,
        use_rag=True
    )

    # Pydantic objects are converted to dictionaries
    # so Python's JSON library can save them.
    comparison = {
        "incident": TEST_INCIDENT,
        "llm_only": llm_result.model_dump(),
        "rag_assisted": rag_result.model_dump()
    }

    output_path = Path("rag_comparison.json")

    output_path.write_text(
        json.dumps(comparison, indent=2),
        encoding="utf-8"
    )

    print("\nEvaluation saved to:", output_path)


if __name__ == "__main__":
    run_evaluation()
