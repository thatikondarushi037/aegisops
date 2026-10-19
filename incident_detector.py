
def calculate_severity(error_rate: float, latency: int) -> str:
    if error_rate > 10 or latency > 1000:
        return "critical"

    if error_rate > 5 or latency > 500:
        return "warning"

    return "normal"


def main():
    incidents = [
        {"service": "payment-service", "error_rate": 18, "latency": 300},
        {"service": "order-service", "error_rate": 3, "latency": 750},
        {"service": "inventory-service", "error_rate": 1, "latency": 120},
    ]

    for incident in incidents:
        severity = calculate_severity(
            incident["error_rate"],
            incident["latency"]
        )

        print(f"Service: {incident['service']}")
        print(f"Severity: {severity}")
        print("-" * 30)


if __name__ == "__main__":
    main()
