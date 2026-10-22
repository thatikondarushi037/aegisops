
from concurrent.futures import ThreadPoolExecutor
import requests

URL = "http://127.0.0.1:8001/incidents"

PAYLOAD = {
    "service": "concurrency-test-service",
    "error_rate": 15.0,
    "latency": 1200
}


def send_alert(_):
    response = requests.post(
        URL,
        json=PAYLOAD,
        timeout=10
    )
    return response.status_code, response.json()


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(send_alert, range(5)))

    for status_code, body in results:
        print("Status:", status_code, "ID:", body.get("id"))

    successful = [
        body["id"]
        for status_code, body in results
        if status_code in (200, 201)
    ]

    print("Unique incident IDs:", set(successful))
