import random
import time 
import requests


from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


SERVICES = [
    "payment-service",
    "login-service",
    "inventory-service"
]



def generate_metrics():
    service = random.choice(SERVICES)

    if random.random() < 0.8:
        error_rate = round(random.uniform(0, 4), 2)
        latency = random.randint(100, 400)
    else:
        error_rate = round(random.uniform(6, 20), 2)
        latency = random.randint(600, 1500)

    return {
        "service": service,
        "error_rate": error_rate,
        "latency": latency
    }

    
def should_alert(metrics):
    return (
        metrics["error_rate"] > 5
        or metrics["latency"] > 500
    )



API_URL = "http://localhost:5678/webhook/aegisops-alert"


return_policy = Retry(
    total=3,
    connect=3,
    read=0,
    backoff_factor=1,
    status_forcelist=[429, 502, 503, 504],
    allowed_methods=frozenset(["POST"]),
    respect_retry_after_header=True,
)

session = requests.Session()

adapter = HTTPAdapter(max_retries=return_policy)


session.mount("http://", adapter)

session.mount("https://", adapter)






def send_metrics(metrics):
    response = requests.post(
        API_URL,
        json=metrics,
        timeout=(3, 5)
    )

    response.raise_for_status()
    return response.json()
    

if __name__ == "__main__":
    for _ in range(5):
        metrics = generate_metrics()
        
        
        if not should_alert(metrics):
            print("Healthy measurment skipped:", metrics)
            time.sleep(1)
            continue
        
        
        try:
            send_metrics(metrics)
            print("Alert delivered to n8n:", metrics)
        except requests.RequestException as error:
            print("Delivery failed:", error)
        time.sleep(1)