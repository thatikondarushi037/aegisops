
import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

from app import app
from database import Base, get_db
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
if test_database_url.database != "aegisops_test":
    raise RuntimeError("Refusing to use a non-test database")

test_engine = create_engine(test_database_url)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=test_engine)

    connection = test_engine.connect()
    transaction = connection.begin()

    def override_get_db():
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint"
        ) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client

    finally:
        app.dependency_overrides.pop(get_db, None)
        transaction.rollback()
        connection.close()
