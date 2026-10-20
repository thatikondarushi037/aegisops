
from models import Incident
import pytest

#unit testing 

def test_critical_incident():
    incident = Incident(
        service="payment-service",
        error_rate=18,
        latency=300
    )

    assert incident.calculate_severity() == "critical"


def test_warning_incident():
    incident = Incident(
        service="order-service",
        error_rate=3,
        latency=750
    )

    assert incident.calculate_severity() == "warning"


def test_normal_incident():
    incident = Incident(
        service="inventory-service",
        error_rate=1,
        latency=120
    )

    assert incident.calculate_severity() == "normal"



#boundary testing was done here 



@pytest.mark.parametrize(
    "error_rate, latency, expected",
    [
        (5, 500, "normal"),
        (5.1, 500, "warning"),
        (10, 1000, "warning"),
        (10.1, 1000, "critical"),
        (10, 1001, "critical"),
    ]
)
def test_severity_boundaries(error_rate, latency, expected):
    incident = Incident(
        service="boundary-test",
        error_rate=error_rate,
        latency=latency
    )

    assert incident.calculate_severity() == expected