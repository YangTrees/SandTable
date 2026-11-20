from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv is optional at runtime
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'sandplay.db'}")
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
COUNSELOR_TOKEN = _env("COUNSELOR_TOKEN", "dev-counselor-token")
MULTIMODAL_API_KEY = _env("MULTIMODAL_API_KEY")
MULTIMODAL_BASE_URL = _env("MULTIMODAL_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MULTIMODAL_MODEL = _env("MULTIMODAL_MODEL", "gpt-4o-mini")
MULTIMODAL_TIMEOUT_SECONDS = int(_env("MULTIMODAL_TIMEOUT_SECONDS", "180"))
ALLOW_DEMO_REPORT = _env("ALLOW_DEMO_REPORT", "true").lower() in {"1", "true", "yes", "on"}
CORS_ORIGINS = [item.strip() for item in _env("CORS_ORIGINS", "*").split(",") if item.strip()]

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
