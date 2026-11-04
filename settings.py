"""Small environment-based configuration shared by API and worker."""

from dataclasses import dataclass
import math
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def number(name, default, minimum, maximum, convert=float):
    value = convert(os.getenv(name, str(default)))
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CHAT_TIMEOUT = number("OLLAMA_CHAT_TIMEOUT_SECONDS", 120, 1, 600)
OLLAMA_EMBED_TIMEOUT = number("OLLAMA_EMBED_TIMEOUT_SECONDS", 30, 1, 300)


@dataclass(frozen=True)
class WorkerSettings:
    poll_seconds: float = 2
    lease_seconds: int = 300
    max_attempts: int = 3
    backoff_seconds: float = 5
    max_backoff_seconds: float = 300

    @classmethod
    def from_env(cls):
        return cls(
            poll_seconds=number("WORKER_POLL_SECONDS", 2, 0.1, 60),
            lease_seconds=number("WORKER_LEASE_SECONDS", 300, 1, 3600, int),
            max_attempts=number("INVESTIGATION_MAX_ATTEMPTS", 3, 1, 10, int),
            backoff_seconds=number("WORKER_BACKOFF_SECONDS", 5, 0, 3600),
            max_backoff_seconds=number("WORKER_MAX_BACKOFF_SECONDS", 300, 1, 3600),
        )
