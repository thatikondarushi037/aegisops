"""Session-bound conversational state; read-only database operations only."""
import json
from threading import BoundedSemaphore
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from assistant_service import Answer, answer_question
from assistant_tools import ReadOnlyTools, require_active, safe_text
from dashboard_auth import browser_session, require_csrf
from database import get_db

router = APIRouter(prefix="/dashboard/api/assistant")
slots = BoundedSemaphore(2)
MAX_TURNS = 6


class Ask(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=2000)
    incident_id: int | None = Field(default=None, ge=1, le=2147483647)


class Turn(BaseModel):
    message: str
    answer: Answer


class Conversation(BaseModel):
    turns: list[Turn] = Field(max_length=MAX_TURNS)
    context_incident_id: int | None


@router.get("", response_model=Conversation)
def conversation(session=Depends(browser_session)):
    if not session.assistant_lock.acquire(blocking=False):
        raise HTTPException(409, "Assistant is still responding")
    try:
        return {"turns": list(session.assistant_history), "context_incident_id": session.assistant_context}
    finally:
        session.assistant_lock.release()


@router.post("/clear", response_model=Conversation)
def clear(session=Depends(require_csrf)):
    if not session.assistant_lock.acquire(blocking=False):
        raise HTTPException(409, "Assistant is still responding")
    try:
        session.assistant_history.clear()
        session.assistant_context = None
        return {"turns": [], "context_incident_id": None}
    finally:
        session.assistant_lock.release()


def respond(body, db, session):
    if not session.assistant_lock.acquire(blocking=False):
        raise HTTPException(409, "Assistant is still responding")
    if not slots.acquire(blocking=False):
        session.assistant_lock.release()
        raise HTTPException(429, "Assistant is busy. Try again shortly")
    try:
        require_active(session)
        message = safe_text(body.message.strip(), 2000)
        if not message:
            raise HTTPException(422, "Enter a question")
        deadline = time.monotonic() + 60
        tools = ReadOnlyTools(db, session, deadline)
        previous = [turn["message"] for turn in session.assistant_history]
        answer = answer_question(message, body.incident_id or session.assistant_context, previous, tools, deadline)
        require_active(session)
        turn = Turn(message=message, answer=answer).model_dump(mode="json")
        session.assistant_history.append(turn)
        del session.assistant_history[:-MAX_TURNS]
        session.assistant_context = answer.context_incident_id
        return turn
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Assistant records are temporarily unavailable") from None
    finally:
        slots.release()
        session.assistant_lock.release()


@router.post("", response_model=Turn)
async def ask(request: Request, session=Depends(require_csrf), db=Depends(get_db)):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 12000:
            raise HTTPException(413, "Assistant request is too large")
    try:
        body = Ask.model_validate(json.loads(data))
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(422, "Provide a question of 1–2000 characters and an optional positive incident ID") from None
    return await run_in_threadpool(respond, body, db, session)
