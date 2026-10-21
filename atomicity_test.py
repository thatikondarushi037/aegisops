
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from db_models import IncidentRecord


db = SessionLocal()

try:
    record = IncidentRecord(
        service="atomicity-test-service",
        error_rate=15,
        latency=400,
        severity="critical"
    )

    db.add(record)
    db.flush()

    print("Incident inserted inside transaction.")

    db.execute(
        text("SELECT * FROM table_that_does_not_exist")
    )

    db.commit()

except SQLAlchemyError as error:
    print("Database error:", type(error).__name__)

    db.rollback()
    print("Transaction rolled back.")

finally:
    db.close()
