"""PostgreSQL-backed worker. Run: python -m worker [--once]."""

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
import logging
import signal
from threading import Event
from uuid import uuid4

import requests
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import engine as default_engine
from db_models import IncidentRecord, InvestigationJob
from investigation_service import generate_investigation, incident_snapshot, save_investigation
from settings import WorkerSettings

logger = logging.getLogger("aegisops.worker")
LOCK_NAMESPACE = 150015  # PostgreSQL two-integer session advisory-lock namespace.


@dataclass(frozen=True)
class Claim:
    job_id: int
    token: str
    incident: dict


def clear_claim(job):
    job.claim_token = None
    job.lease_expires_at = None


def unlock(connection, job_id):
    try:
        connection.execute(text("SELECT pg_advisory_unlock(:namespace, :id)"),
                           {"namespace": LOCK_NAMESPACE, "id": job_id})
    except SQLAlchemyError:
        # Never return a session with a possibly-held advisory lock to the pool.
        connection.invalidate()


@contextmanager
def claim_job(engine, config):
    """Short row-lock transaction; keep only a session advisory lock in flight.

    SKIP LOCKED distributes work. A claim token fences stale writes after
    recovery. An advisory lock additionally keeps a still-connected slow
    worker's expired lease from causing concurrent model calls.
    """
    job_id = None
    claim = None
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_connection:
        try:
            with Session(engine) as db, db.begin():
                now = db.scalar(select(func.now()))
                ready = or_(
                    and_(InvestigationJob.status == "pending", InvestigationJob.next_attempt_at <= now),
                    and_(InvestigationJob.status == "running", InvestigationJob.lease_expires_at <= now),
                )
                jobs = db.scalars(
                    select(InvestigationJob).where(ready)
                    .order_by(InvestigationJob.next_attempt_at, InvestigationJob.id)
                    .limit(32).with_for_update(skip_locked=True)
                ).all()
                for job in jobs:
                    acquired = lock_connection.scalar(
                        text("SELECT pg_try_advisory_lock(:namespace, :id)"),
                        {"namespace": LOCK_NAMESPACE, "id": job.id},
                    )
                    if not acquired:
                        continue
                    job_id = job.id
                    if job.attempts >= job.max_attempts:
                        job.status = "failed"
                        job.error_category = "attempts_exhausted"
                        job.error_message = "Worker claim expired after the final allowed attempt."
                        job.updated_at = now
                        clear_claim(job)
                        unlock(lock_connection, job_id)
                        job_id = None
                        continue
                    incident = db.get(IncidentRecord, job.incident_id)
                    token = str(uuid4())
                    job.status = "running"
                    job.attempts += 1
                    job.updated_at = now
                    job.lease_expires_at = now + timedelta(seconds=config.lease_seconds)
                    job.claim_token = token
                    job.error_category = None
                    job.error_message = None
                    claim = Claim(job.id, token, incident_snapshot(incident))
                    break
            # No database transaction is held while this context is yielded.
            yield claim
        finally:
            if job_id is not None:
                unlock(lock_connection, job_id)


def complete_job(engine, claim, result):
    """Persist exactly one result and completion in the same transaction."""
    with Session(engine) as db, db.begin():
        job = db.scalar(select(InvestigationJob).where(
            InvestigationJob.id == claim.job_id).with_for_update())
        if job is None:
            return None  # Incident was explicitly deleted while inference ran.
        if job.status == "completed":
            return job.investigation_id  # Completion/ack retry after commit.
        if job.status != "running" or job.claim_token != claim.token:
            return None  # Recovered by another worker; stale result is discarded.
        record = save_investigation(db, result, claim.incident)
        now = db.scalar(select(func.now()))
        job.investigation_id = record.id
        job.status = "completed"
        job.updated_at = now
        job.error_category = None
        job.error_message = None
        clear_claim(job)
        return record.id


def sanitized_error(error):
    # Fixed strings only: exception text can contain URLs, credentials, model
    # content, database parameters, or traces. Never persist or log that text.
    if isinstance(error, requests.Timeout):
        return "model_timeout", "The model request timed out."
    if isinstance(error, requests.RequestException):
        return "model_unavailable", "The model service could not complete the request."
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "invalid_result", "The model result did not pass investigation validation."
    if isinstance(error, SQLAlchemyError):
        return "database_error", "Investigation persistence could not complete."
    return "internal_error", "The investigation attempt could not complete."


def fail_job(engine, claim, error, config):
    with Session(engine) as db, db.begin():
        job = db.scalar(select(InvestigationJob).where(
            InvestigationJob.id == claim.job_id).with_for_update())
        if job is None or job.status != "running" or job.claim_token != claim.token:
            return
        now = db.scalar(select(func.now()))
        job.error_category, job.error_message = sanitized_error(error)
        job.status = "failed" if job.attempts >= job.max_attempts else "pending"
        delay = min(config.max_backoff_seconds, config.backoff_seconds * 2 ** (job.attempts - 1))
        job.next_attempt_at = now + timedelta(seconds=delay)
        job.updated_at = now
        clear_claim(job)


def process_one(engine=default_engine, config=None, investigator=None):
    config = config or WorkerSettings.from_env()
    with claim_job(engine, config) as claim:
        if claim is None:
            return False
        try:
            result = generate_investigation(claim.incident, investigator=investigator)
            result_id = complete_job(engine, claim, result)
            logger.info("Job %s finished; result saved=%s", claim.job_id, result_id is not None)
        except Exception as error:
            fail_job(engine, claim, error, config)
            logger.warning("Job %s attempt failed: %s", claim.job_id, sanitized_error(error)[0])
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one eligible job, then exit")
    args = parser.parse_args()
    config = WorkerSettings.from_env()
    stop = Event()

    def request_stop(signum, frame):
        stop.set()  # Finish current attempt; stop claiming new jobs.

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        while not stop.is_set():
            try:
                processed = process_one(config=config)
            except Exception:
                # If DB is down, the durable lease recovers later. No traceback
                # or raw exception text is emitted by the worker.
                logger.error("Worker database cycle failed; retrying after poll interval")
                processed = False
            if args.once:
                break
            if not processed:
                stop.wait(config.poll_seconds)
    finally:
        default_engine.dispose()


if __name__ == "__main__":
    main()
