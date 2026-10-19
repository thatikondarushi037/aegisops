
class Incident:
    def __init__(self, service: str, error_rate: float, latency: int):
        self.service = service
        self.error_rate = error_rate
        self.latency = latency

    def calculate_severity(self) -> str:
        if self.error_rate > 10 or self.latency > 1000:
            return "critical"

        if self.error_rate > 5 or self.latency > 500:
            return "warning"

        return "normal"
