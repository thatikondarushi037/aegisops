
from rag_retriever import retrieve_runbooks


# Each test contains a query and the runbook we expect.
TEST_CASES = [
    {
        "query": "Payment transactions are failing and timing out",
        "expected": "payment_service.md"
    },
    {
        "query": "Users cannot log in due to token validation failures",
        "expected": "login_service.md"
    },
    {
        "query": "Inventory event queue is delayed",
        "expected": "inventory_service.md"
    },
    {
        "query": "Payment database connections are exhausted",
        "expected": "payment_service.md"
    },
    {
        "query": "Redis session store unavailable during login",
        "expected": "login_service.md"
    },
    {
        "query": "Stock synchronization jobs are failing",
        "expected": "inventory_service.md"
    }
]

def evaluate_retrieval():
    correct = 0

    for index, case in enumerate(TEST_CASES, start=1):
        matches = retrieve_runbooks(
            case["query"],
            top_k=1
        )

        predicted = (
            matches[0]["source"]
            if matches else None
        )

        passed = predicted == case["expected"]

        if passed:
            correct += 1

        print(
            f"Test {index}: "
            f"Expected={case['expected']} | "
            f"Retrieved={predicted} | "
            f"Passed={passed}"
        )

    total = len(TEST_CASES)
    accuracy = correct / total if total else 0

    print(f"\nCorrect: {correct}/{total}")
    print(f"Top-1 retrieval accuracy: {accuracy:.2%}")


if __name__ == "__main__":
    evaluate_retrieval()
