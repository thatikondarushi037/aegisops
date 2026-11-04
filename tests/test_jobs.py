from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread

from fastapi.testclient import TestClient
import pytest
import requests
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import app as app_module
from conftest import migrate
from database import get_db
from db_models import IncidentRecord, InvestigationJob, InvestigationRecord
from investigation_schema import InvestigationResult
from settings import WorkerSettings
from worker import claim_job, complete_job, fail_job, process_one

CONFIG = WorkerSettings(backoff_seconds=0)
PAYLOAD = {"service": "payment-service", "error_rate": 15, "latency": 1200}


def fake_model(incident):
    return InvestigationResult(
        incident_id=incident["id"], suspected_root_cause="Unknown",
        evidence=["Untrusted model evidence"], recommended_action="Inspect service logs",
        confidence="high", requires_human_approval=True,
    )


@pytest.fixture
def committed_client(migrated_engine):
    def override():
        with Session(migrated_engine) as db:
            yield db

    app_module.app.dependency_overrides[get_db] = override
    try:
        with TestClient(app_module.app) as client:
            yield client
    finally:
        app_module.app.dependency_overrides.pop(get_db, None)


def ingest(client):
    response = client.post("/incidents", json=PAYLOAD)
    assert response.status_code == 201
    return response.json()["id"]


def job_status(client, incident_id):
    response = client.get(f"/incidents/{incident_id}/investigation-job")
    assert response.status_code == 200
    assert "claim_token" not in response.json()
    return response.json()


def test_ingestion_is_atomic_pending_and_no_inference(committed_client, migrated_engine, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Ingestion must not call the model")

    monkeypatch.setattr(app_module, "investigate_incident", forbidden)
    incident_id = ingest(committed_client)
    duplicate = committed_client.post("/incidents", json=PAYLOAD)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == incident_id
    job = job_status(committed_client, incident_id)
    assert job["status"] == "pending"
    assert job["attempts"] == 0
    assert job["lease_expires_at"] is None
    with Session(migrated_engine) as db:
        assert db.scalar(select(func.count()).select_from(InvestigationJob)) == 1
    with pytest.raises(IntegrityError):
        with Session(migrated_engine) as db, db.begin():
            db.add(InvestigationJob(incident_id=incident_id))


def test_job_insert_failure_rolls_back_incident(committed_client, migrated_engine):
    def reject_job(session, context, instances):
        if any(isinstance(item, InvestigationJob) for item in session.new):
            raise SQLAlchemyError("synthetic failure")

    event.listen(Session, "before_flush", reject_job)
    try:
        assert committed_client.post("/incidents", json=PAYLOAD).status_code == 500
    finally:
        event.remove(Session, "before_flush", reject_job)
    with Session(migrated_engine) as db:
        assert db.scalar(select(func.count()).select_from(IncidentRecord)) == 0
        assert db.scalar(select(func.count()).select_from(InvestigationJob)) == 0


def test_worker_success_and_history(committed_client, migrated_engine):
    incident_id = ingest(committed_client)

    def model_outside_transaction(incident):
        with migrated_engine.connect() as connection:
            assert connection.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND state='idle in transaction' AND pid<>pg_backend_pid() "
                "AND query LIKE '%investigation_jobs%'"
            )).scalar_one() == 0
        return fake_model(incident)

    assert process_one(migrated_engine, CONFIG, model_outside_transaction)
    job = job_status(committed_client, incident_id)
    assert job["status"] == "completed"
    assert job["attempts"] == 1
    assert job["investigation_id"] is not None
    assert job["lease_expires_at"] is None
    history = committed_client.get(f"/incidents/{incident_id}/investigations").json()
    assert len(history) == 1
    assert history[0]["id"] == job["investigation_id"]
    assert history[0]["requires_human_approval"] is True
    assert history[0]["confidence"] == "low"
    assert len(history[0]["evidence"]) == 2
    assert "Untrusted model evidence" not in history[0]["evidence"]
    assert not process_one(migrated_engine, CONFIG, fake_model)


def test_retry_backoff_then_terminal_failure(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    with Session(migrated_engine) as db, db.begin():
        db.scalar(select(InvestigationJob)).max_attempts = 2
    secret = "DO_NOT_LEAK_MODEL_CREDENTIAL"

    def failure(incident):
        raise requests.Timeout(secret)

    config = replace(CONFIG, backoff_seconds=10)
    assert process_one(migrated_engine, config, failure)
    first = job_status(committed_client, incident_id)
    assert first["status"] == "pending"
    assert first["attempts"] == 1
    assert first["error_category"] == "model_timeout"
    assert secret not in str(first)
    assert not process_one(migrated_engine, config, failure)
    with Session(migrated_engine) as db, db.begin():
        db.scalar(select(InvestigationJob)).next_attempt_at = db.scalar(select(func.now())) - timedelta(seconds=1)
    assert process_one(migrated_engine, config, failure)
    terminal = job_status(committed_client, incident_id)
    assert terminal["status"] == "failed"
    assert terminal["attempts"] == 2
    assert terminal["lease_expires_at"] is None
    assert not process_one(migrated_engine, config, failure)


@pytest.mark.parametrize("kind", ["approval", "identity", "root_cause", "malformed"])
def test_unsafe_results_never_persist(committed_client, migrated_engine, kind):
    incident_id = ingest(committed_client)

    def unsafe(incident):
        result = fake_model(incident)
        if kind == "approval":
            result.requires_human_approval = False
        elif kind == "identity":
            result.incident_id += 999
        elif kind == "root_cause":
            result.suspected_root_cause = "Definitely the database"
        else:
            return {"bad": "schema"}
        return result

    assert process_one(migrated_engine, CONFIG, unsafe)
    assert job_status(committed_client, incident_id)["error_category"] == "invalid_result"
    assert committed_client.get(f"/incidents/{incident_id}/investigations").json() == []


def test_multiple_workers_and_expired_live_owner(committed_client, migrated_engine):
    ingest(committed_client)
    with claim_job(migrated_engine, CONFIG) as first:
        assert first is not None
        # Expiry alone must not create overlap with a connected live owner.
        with Session(migrated_engine) as db, db.begin():
            db.get(InvestigationJob, first.job_id).lease_expires_at = db.scalar(select(func.now())) - timedelta(seconds=1)

        def second_worker():
            with claim_job(migrated_engine, CONFIG) as second:
                return second

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(lambda _: second_worker(), range(2))) == [None, None]
        # A valid owner can finish even if its original lease expired.
        assert complete_job(migrated_engine, first, fake_model(first.incident)) is not None


def test_abandoned_claim_recovered_and_stale_completion_rejected(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    with claim_job(migrated_engine, CONFIG) as abandoned:
        assert abandoned is not None
    with Session(migrated_engine) as db, db.begin():
        job = db.get(InvestigationJob, abandoned.job_id)
        job.lease_expires_at = db.scalar(select(func.now())) - timedelta(seconds=1)
    with claim_job(migrated_engine, CONFIG) as recovered:
        assert recovered.job_id == abandoned.job_id
        assert recovered.token != abandoned.token
        assert complete_job(migrated_engine, abandoned, fake_model(abandoned.incident)) is None
        fail_job(migrated_engine, abandoned, RuntimeError("stale"), CONFIG)
        result_id = complete_job(migrated_engine, recovered, fake_model(recovered.incident))
        # Simulate a lost acknowledgement after the success transaction commits.
        assert complete_job(migrated_engine, recovered, fake_model(recovered.incident)) == result_id
    assert job_status(committed_client, incident_id)["attempts"] == 2
    assert len(committed_client.get(f"/incidents/{incident_id}/investigations").json()) == 1


def test_expired_final_attempt_becomes_failed(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    with Session(migrated_engine) as db, db.begin():
        db.scalar(select(InvestigationJob)).max_attempts = 1
    with claim_job(migrated_engine, CONFIG) as abandoned:
        pass
    with Session(migrated_engine) as db, db.begin():
        db.get(InvestigationJob, abandoned.job_id).lease_expires_at = db.scalar(select(func.now())) - timedelta(seconds=1)
    assert not process_one(migrated_engine, CONFIG, fake_model)
    job = job_status(committed_client, incident_id)
    assert job["status"] == "failed"
    assert job["error_category"] == "attempts_exhausted"


def test_result_and_completion_are_atomic(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    with claim_job(migrated_engine, CONFIG) as claim:
        def fail_completion(session, context, instances):
            if any(isinstance(item, InvestigationJob) and item.status == "completed" for item in session.dirty):
                raise SQLAlchemyError("synthetic completion failure")

        event.listen(Session, "before_flush", fail_completion)
        try:
            with pytest.raises(SQLAlchemyError):
                complete_job(migrated_engine, claim, fake_model(claim.incident))
        finally:
            event.remove(Session, "before_flush", fail_completion)
        assert committed_client.get(f"/incidents/{incident_id}/investigations").json() == []
        assert job_status(committed_client, incident_id)["status"] == "running"
        assert complete_job(migrated_engine, claim, fake_model(claim.incident)) is not None


def test_manual_and_automatic_investigations_coexist(committed_client, migrated_engine, monkeypatch):
    incident_id = ingest(committed_client)
    monkeypatch.setattr(app_module, "investigate_incident", fake_model)
    assert committed_client.post(f"/incidents/{incident_id}/investigate").status_code == 200
    assert job_status(committed_client, incident_id)["status"] == "pending"
    assert process_one(migrated_engine, CONFIG, fake_model)
    assert len(committed_client.get(f"/incidents/{incident_id}/investigations").json()) == 2


@pytest.mark.parametrize("error,expected", [
    (requests.Timeout("private timeout details"), 504),
    (requests.ConnectionError("private URL credentials"), 502),
    (ValueError("private model content"), 502),
])
def test_manual_failure_is_controlled(committed_client, monkeypatch, error, expected):
    incident_id = ingest(committed_client)

    def failure(incident):
        raise error

    monkeypatch.setattr(app_module, "investigate_incident", failure)
    response = committed_client.post(f"/incidents/{incident_id}/investigate")
    assert response.status_code == expected
    assert "private" not in response.text
    assert committed_client.get(f"/incidents/{incident_id}/investigations").json() == []
    assert job_status(committed_client, incident_id)["status"] == "pending"


def test_delete_uninvestigated_incident_preserves_existing_api(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    assert committed_client.delete(f"/incidents/{incident_id}").status_code == 204
    with Session(migrated_engine) as db:
        assert db.scalar(select(func.count()).select_from(InvestigationJob)) == 0


def test_job_status_not_found(committed_client, migrated_engine):
    assert committed_client.get("/incidents/99999999/investigation-job").status_code == 404
    with Session(migrated_engine) as db, db.begin():
        record = IncidentRecord(service="legacy", error_rate=1, latency=100, severity="normal")
        db.add(record)
        db.flush()
        incident_id = record.id
    response = committed_client.get(f"/incidents/{incident_id}/investigation-job")
    assert response.status_code == 404
    assert response.json()["detail"] == "Automatic investigation job not found"


def test_v015_upgrade_preserves_v014_history(schema_engine):
    migrate(schema_engine, "c14a0e7d921b")
    with Session(schema_engine) as db, db.begin():
        incident = IncidentRecord(service="legacy", error_rate=15, latency=1200, severity="critical")
        db.add(incident)
        db.flush()
        db.add(InvestigationRecord(**fake_model({"id": incident.id}).model_dump()))
    with schema_engine.connect() as c:
        before = {table: c.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
                  for table in ("incidents", "investigations")}
    migrate(schema_engine)
    with schema_engine.connect() as c:
        for table, rows in before.items():
            assert c.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
        assert c.execute(text("SELECT count(*) FROM investigation_jobs")).scalar_one() == 0


def test_standalone_worker_with_mock_ollama(committed_client, migrated_engine):
    """Exercise CLI/config/RAG/network/worker in a separate Python process."""
    incident_id = ingest(committed_client)
    calls = []

    class MockOllama(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, payload["model"]))
            if self.path == "/api/embed":
                body = {"embeddings": [[1.0, 0.5] for _ in payload["input"]]}
            elif self.path == "/api/chat":
                model_incident_id = int(re.search(r"INCIDENT ID: (\d+)", payload["messages"][1]["content"])[1])
                body = {"message": {"content": fake_model({"id": model_incident_id}).model_dump_json()}}
            else:
                self.send_error(404)
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), MockOllama)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = migrated_engine.url
    with migrated_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert url.database == "aegisops_test"
    assert schema.startswith("test_v014_")
    env = os.environ.copy()
    env.update({
        "DB_HOST": url.host, "DB_PORT": str(url.port), "DB_NAME": "aegisops_test",
        "DB_USER": url.username, "DB_PASSWORD": url.password,
        "PGOPTIONS": f"-csearch_path={schema}",
        "OLLAMA_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "OLLAMA_CHAT_MODEL": "mock-chat", "OLLAMA_EMBED_MODEL": "mock-embed",
    })
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "worker", "--once"],
            cwd=Path(__file__).resolve().parents[1], env=env,
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, "Standalone worker failed"
        assert job_status(committed_client, incident_id)["status"] == "completed"
        assert calls.count(("/api/embed", "mock-embed")) == 2
        assert calls.count(("/api/chat", "mock-chat")) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(os.getenv("AEGISOPS_REAL_MODEL_SMOKE") != "1", reason="Optional real Ollama/RAG smoke; opt in explicitly")
def test_optional_real_model_smoke(committed_client, migrated_engine):
    incident_id = ingest(committed_client)
    assert process_one(migrated_engine, CONFIG)
    assert job_status(committed_client, incident_id)["status"] == "completed"
    assert len(committed_client.get(f"/incidents/{incident_id}/investigations").json()) == 1
