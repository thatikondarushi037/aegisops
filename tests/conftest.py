
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session

from app import app
from database import database_url, get_db
import db_models


load_dotenv()

test_database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "5432")),
    database="aegisops_test",
)

# Safety check before connecting
if (test_database_url.database != "aegisops_test"
        or database_url.database == test_database_url.database):
    raise RuntimeError("Refusing to use a non-test database")

def migrate(engine, revision="head"):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


@pytest.fixture
def schema_engine():
    """Only create/drop this test's generated schema in aegisops_test."""
    schema = "test_v014_" + uuid4().hex
    admin = create_engine(test_database_url)
    try:
        with admin.begin() as connection:
            if not connection.execute(text(
                "SELECT has_database_privilege(current_user, current_database(), 'CREATE')"
            )).scalar_one():
                pytest.fail(
                    "Test role needs CREATE on aegisops_test for isolated migration schemas; "
                    "ask the database owner for this test-only grant.",
                    pytrace=False,
                )
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except BaseException:
        admin.dispose()
        raise
    engine = create_engine(
        test_database_url,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def migrated_engine(schema_engine):
    migrate(schema_engine)
    return schema_engine


@pytest.fixture
def client(migrated_engine):
    connection = migrated_engine.connect()
    transaction = connection.begin()

    def override_get_db():
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint"
        ) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app, headers={"Authorization": "Bearer test-only-operator"}) as test_client:
            yield test_client

    finally:
        app.dependency_overrides.pop(get_db, None)
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def local_test_credentials(monkeypatch):
    """Exercise real authentication with disposable credentials, never deployment secrets."""
    monkeypatch.setenv("AEGISOPS_OPERATOR_TOKEN", "test-only-operator")
    monkeypatch.setenv("AEGISOPS_N8N_TOKEN", "test-only-ingest")
