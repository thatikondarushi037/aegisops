from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app as app_module
from database import Base, get_db
from conftest import migrate


PREVIOUS = "f52e0932e446"
LATEST = "c14a0e7d921b"


def insert_incident(connection, service="migration-test", status="open"):
    return connection.execute(text(
        "INSERT INTO incidents(service,error_rate,latency,severity,status,created_at) "
        "VALUES (:service,15,1200,'critical',:status,CURRENT_TIMESTAMP) RETURNING id"
    ), {"service": service, "status": status}).scalar_one()


def test_fresh_upgrade_index_and_metadata(migrated_engine):
    with migrated_engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == LATEST
        index = next(i for i in inspect(connection).get_indexes("incidents")
                     if i["name"] == "uq_incidents_open_service")
        assert index["unique"] is True
        assert index["column_names"] == ["service"]
        assert "open" in str(index["dialect_options"]["postgresql_where"])
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    with migrated_engine.begin() as connection:
        insert_incident(connection)
        insert_incident(connection, status="resolved")
        insert_incident(connection, status="resolved")
    with pytest.raises(IntegrityError):
        with migrated_engine.begin() as connection:
            insert_incident(connection)


def test_existing_upgrade_preserves_history_and_foreign_key(schema_engine):
    migrate(schema_engine, PREVIOUS)
    with schema_engine.begin() as connection:
        incident_id = insert_incident(connection)
        connection.execute(text(
            "INSERT INTO investigations(incident_id,suspected_root_cause,evidence,"
            "recommended_action,confidence,requires_human_approval,created_at) "
            "VALUES (:id,'Unknown','[]','Inspect logs','low',true,CURRENT_TIMESTAMP)"
        ), {"id": incident_id})
        before = {table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
                  for table in ("incidents", "investigations")}
    migrate(schema_engine)
    with schema_engine.connect() as connection:
        for table, rows in before.items():
            assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
        assert inspect(connection).get_foreign_keys("investigations")[0]["referred_table"] == "incidents"
    with pytest.raises(IntegrityError):
        with schema_engine.begin() as connection:
            connection.execute(text("DELETE FROM incidents WHERE id=:id"), {"id": incident_id})


def test_duplicate_preflight_stops_without_changing_records(schema_engine):
    migrate(schema_engine, PREVIOUS)
    with schema_engine.begin() as connection:
        ids = [insert_incident(connection), insert_incident(connection)]
        before = connection.execute(text("SELECT * FROM incidents ORDER BY id")).all()
    with pytest.raises(RuntimeError, match="duplicate open incident ID groups") as error:
        migrate(schema_engine)
    assert str(ids) in str(error.value)
    with schema_engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM incidents ORDER BY id")).all() == before
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == PREVIOUS
        assert not inspect(connection).get_indexes("incidents")


def test_concurrent_ingestion_reuses_one_incident(migrated_engine, monkeypatch):
    # Force all requests past the initial lookup before any inserts. This
    # exercises the database conflict recovery branch, not just serial reuse.
    workers = 5
    barrier = Barrier(workers)
    original_find = app_module.find_open_incident

    def synchronized_find(db, service):
        result = original_find(db, service)
        if not db.info.get("initial_lookup_done"):
            db.info["initial_lookup_done"] = True
            barrier.wait(timeout=15)
        return result

    def override_get_db():
        with Session(migrated_engine) as db:
            yield db

    monkeypatch.setattr(app_module, "find_open_incident", synchronized_find)
    app_module.app.dependency_overrides[get_db] = override_get_db
    payload = {"service": "concurrency-v014", "error_rate": 15, "latency": 1200}
    try:
        def send(_):
            with TestClient(app_module.app) as client:
                return client.post("/incidents", json=payload)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            responses = list(pool.map(send, range(workers)))
        assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 201]
        assert len({r.json()["id"] for r in responses}) == 1
        with migrated_engine.connect() as connection:
            assert connection.execute(text(
                "SELECT count(*) FROM incidents WHERE service=:service AND status='open'"
            ), {"service": payload["service"]}).scalar_one() == 1
    finally:
        app_module.app.dependency_overrides.pop(get_db, None)
