from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import app
import dashboard_auth as auth
from database import get_db
from db_models import InvestigationJob, InvestigationRecord

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "dashboard-test-only-password"
PAYLOAD = {"service": "payments-api", "error_rate": 15, "latency": 1200}


@pytest.fixture(autouse=True)
def dashboard_settings(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD_HASH", auth.password_hash(PASSWORD))
    monkeypatch.setenv("DASHBOARD_ORIGIN", "http://testserver")
    auth.sessions.clear()
    auth.attempts.clear()
    yield
    auth.sessions.clear()
    auth.attempts.clear()


@pytest.fixture
def browser(client):
    response = client.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
    assert response.status_code == 200
    return client


def ingest(client, **updates):
    response = client.post("/incidents", json=dict(PAYLOAD, **updates))
    assert response.status_code == 201
    return response.json()["id"]


def test_public_shell_and_security_headers():
    with TestClient(app) as c:
        r = c.get("/dashboard")
        assert r.status_code == 200
        assert "AegisOps" in r.text
        assert r.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert "unsafe-inline" not in r.headers["content-security-policy"]
        assert c.get("/dashboard/assets/app.js").status_code == 200
        assert c.get("/dashboard/assets/.env").status_code == 404


@pytest.mark.parametrize("path", ["overview", "incidents", "jobs", "incidents/1", "incidents/1/history"])
def test_dashboard_requires_session(path):
    with TestClient(app) as c:
        assert c.get("/dashboard/api/" + path).status_code == 401
        assert c.get("/dashboard/api/" + path, headers={"Authorization": "Bearer test-only-ingest"}).status_code == 401


def test_session_cookie_and_no_api_token_disclosure():
    with TestClient(app) as c:
        r = c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/dashboard" in cookie
        assert r.json()["expires_in"] == 3600
        assert "csrf_token" in r.json()
        assert PASSWORD not in r.text and "test-only-operator" not in r.text
        assert c.get("/dashboard/session").status_code == 200
        # Browser sessions cannot use original mutating or reading Bearer APIs.
        assert c.get("/incidents").status_code == 401
        assert c.post("/incidents", json=PAYLOAD).status_code == 401


def test_login_origin_and_errors_are_sanitized():
    with TestClient(app) as c:
        assert c.post("/dashboard/login", json={"password": PASSWORD}).status_code == 403
        assert c.post("/dashboard/login", json={"password": PASSWORD}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert c.post("/dashboard/login", json={"password": "private-wrong-password"}, headers=ORIGIN).status_code == 401
        r = c.post("/dashboard/login", json={"password": "private" * 600}, headers=ORIGIN)
        assert r.status_code in (400, 413) and "private" not in r.text
        assert c.post("/dashboard/login", content="bad-json", headers=ORIGIN).status_code == 400


def test_login_limit_and_fail_closed(monkeypatch):
    with TestClient(app) as c:
        for _ in range(5):
            assert c.post("/dashboard/login", json={"password": "wrong"}, headers=ORIGIN).status_code == 401
        assert c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN).status_code == 429
        monkeypatch.delenv("DASHBOARD_PASSWORD_HASH")
        assert c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN).status_code == 503


def test_csrf_logout_rotation_and_expiration():
    with TestClient(app) as c:
        first = c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
        old = c.cookies.get(auth.COOKIE)
        current = c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
        assert old not in auth.sessions
        assert c.post("/dashboard/logout", headers=ORIGIN).status_code == 403
        assert c.post("/dashboard/logout", headers={"X-CSRF-Token": current.json()["csrf_token"]}).status_code == 403
        assert c.post("/dashboard/logout", headers=dict(ORIGIN, **{"X-CSRF-Token": current.json()["csrf_token"]})).status_code == 204
        assert c.get("/dashboard/session").status_code == 401
        c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
        auth.sessions[c.cookies.get(auth.COOKIE)].expires = time.monotonic() - 1
        assert c.get("/dashboard/session").status_code == 401


def test_cross_site_and_wrong_host(browser):
    assert browser.get("/dashboard/api/overview", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert browser.get("/dashboard/api/overview", headers={"Host": "evil.example"}).status_code == 403


def test_empty_database(browser):
    summary = browser.get("/dashboard/api/overview").json()
    assert summary["total_incidents"] == summary["open_incidents"] == 0
    assert summary["jobs"] == dict(pending=0, running=0, completed=0, failed=0)
    assert browser.get("/dashboard/api/incidents").json()["items"] == []
    assert browser.get("/dashboard/api/jobs").json()["total"] == 0


def test_filters_pagination_and_correct_statistics(browser):
    ingest(browser)
    ingest(browser, service="Inventory", error_rate=7, latency=600)
    ingest(browser, service="literal%_service", error_rate=1, latency=50)
    summary = browser.get("/dashboard/api/overview").json()
    assert (summary["total_incidents"], summary["open_incidents"], summary["critical_incidents"], summary["warning_incidents"]) == (3, 3, 1, 1)
    assert summary["jobs"] == dict(pending=3, running=0, completed=0, failed=0)
    page = browser.get("/dashboard/api/incidents?service=INVENT&severity=warning&status=open").json()
    assert page["total"] == 1 and page["items"][0]["service"] == "Inventory"
    assert page["items"][0]["job_status"] == "pending"
    assert browser.get("/dashboard/api/incidents?service=%25_").json()["total"] == 1
    first = browser.get("/dashboard/api/incidents?limit=1").json()
    second = browser.get("/dashboard/api/incidents?limit=1&offset=1").json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["limit"] == 1 and first["total"] == 3
    assert browser.get("/dashboard/api/incidents?offset=100").json()["items"] == []
    assert browser.get("/dashboard/api/jobs?status=completed").json()["items"] == []


@pytest.mark.parametrize("path", ["incidents?limit=101", "incidents?offset=-1", "jobs?limit=0", "jobs?status=bogus", "incidents?severity=bogus", "incidents/1/history?limit=51"])
def test_invalid_query_bounds(browser, path):
    assert browser.get("/dashboard/api/" + path).status_code == 422


def test_detail_history_and_job_statuses(browser):
    incident_id = ingest(browser)
    with contextmanager(app.dependency_overrides[get_db])() as db:
        job = db.scalar(select(InvestigationJob))
        job.status = "failed"
        job.attempts = job.max_attempts
        job.error_category = "model_timeout"
        job.error_message = "The model request timed out."
        for _ in range(2):
            db.add(InvestigationRecord(incident_id=incident_id, suspected_root_cause='<img src=x onerror="alert(1)">', evidence=['<script>evil()</script>'], recommended_action="Review logs", confidence="low", requires_human_approval=True))
        db.commit()
    detail = browser.get(f"/dashboard/api/incidents/{incident_id}")
    assert detail.status_code == 200
    assert detail.json()["job"]["status"] == "failed"
    assert "claim_token" not in detail.text
    history = browser.get(f"/dashboard/api/incidents/{incident_id}/history?limit=1").json()
    assert history["total"] == 2 and len(history["items"]) == 1
    assert history["items"][0]["requires_human_approval"] is True
    assert browser.get("/dashboard/api/jobs?status=failed").json()["items"][0]["error_category"] == "model_timeout"
    assert browser.get("/dashboard/api/overview").json()["jobs"]["failed"] == 1
    assert browser.get("/dashboard/api/incidents/999999").status_code == 404


def test_database_failure_is_sanitized(browser, monkeypatch):
    def failure(*args, **kwargs):
        raise SQLAlchemyError("private-db-password")
    monkeypatch.setattr(Session, "execute", failure)
    r = browser.get("/dashboard/api/overview")
    assert r.status_code == 503
    assert "private" not in r.text


def test_all_job_distribution_states_and_legacy_incidents(browser):
    from db_models import IncidentRecord
    ids = [ingest(browser, service="state-" + str(i)) for i in range(4)]
    with contextmanager(app.dependency_overrides[get_db])() as db:
        jobs = db.scalars(select(InvestigationJob).order_by(InvestigationJob.id)).all()
        jobs[1].status = "running"
        jobs[1].attempts = 1
        jobs[1].claim_token = "test-claim"
        jobs[1].lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        record = InvestigationRecord(incident_id=ids[2], suspected_root_cause="Unknown", evidence=["Observed metrics"], recommended_action="Review", confidence="low", requires_human_approval=True)
        db.add(record)
        db.flush()
        jobs[2].status = "completed"
        jobs[2].attempts = 1
        jobs[2].investigation_id = record.id
        jobs[3].status = "failed"
        jobs[3].attempts = jobs[3].max_attempts
        legacy = IncidentRecord(service="legacy", error_rate=0, latency=0, severity="normal", status="superseded")
        db.add(legacy)
        db.flush()
        legacy_id = legacy.id
        db.commit()
    assert browser.get("/dashboard/api/overview").json()["jobs"] == dict(pending=1, running=1, completed=1, failed=1)
    assert browser.get(f"/dashboard/api/incidents/{legacy_id}").json()["job"] is None
    assert browser.get("/dashboard/api/incidents?status=superseded").json()["total"] == 1
    assert browser.get(f"/dashboard/api/incidents/{legacy_id}/history").json()["total"] == 0


def test_secure_cookie_option(monkeypatch):
    monkeypatch.setenv("DASHBOARD_COOKIE_SECURE", "1")
    with TestClient(app) as c:
        r = c.post("/dashboard/login", json={"password": PASSWORD}, headers=ORIGIN)
        assert "secure" in r.headers["set-cookie"].lower()


def test_frontend_contracts():
    if not shutil.which("node"):
        pytest.skip("Node.js required for frontend contract tests")
    result = subprocess.run(["node", "--test", str(Path(__file__).with_name("dashboard_frontend.mjs"))],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
