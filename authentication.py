"""Fail-closed local API roles. Credentials are never returned or logged."""
import os
from secrets import compare_digest

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    operator = os.getenv("AEGISOPS_OPERATOR_TOKEN", "")
    ingest = os.getenv("AEGISOPS_N8N_TOKEN", "")
    if not operator or not ingest or compare_digest(operator.encode(), ingest.encode()):
        raise HTTPException(503, "API authentication is not configured")
    supplied = credentials.credentials.encode() if credentials else b""
    is_operator = compare_digest(supplied, operator.encode())
    is_ingest = compare_digest(supplied, ingest.encode())
    if not (is_operator or is_ingest):
        raise HTTPException(401, "Invalid or missing credentials", headers={"WWW-Authenticate": "Bearer"})
    return "operator" if is_operator else "ingest"


def require_operator(role=Depends(principal)):
    if role != "operator":
        raise HTTPException(403, "Insufficient permission")


def require_ingest(role=Depends(principal)):
    return role
