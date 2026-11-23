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


APP_ENV = _env("APP_ENV", "development").lower()
DATA_DIR = Path(_env("DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{DATA_DIR / 'sandplay.db'}")
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# 服务令牌只用于受控运维脚本。默认关闭，且不再提供任何内置默认值。
COUNSELOR_TOKEN = _env("COUNSELOR_TOKEN")
ENABLE_SERVICE_TOKEN = _env("ENABLE_SERVICE_TOKEN", "false").lower() in {"1", "true", "yes", "on"}

ADMIN_INITIAL_ACCOUNT = _env("ADMIN_INITIAL_ACCOUNT", "admin")
ADMIN_INITIAL_NAME = _env("ADMIN_INITIAL_NAME", "系统管理员")
ADMIN_INITIAL_PASSWORD = _env("ADMIN_INITIAL_PASSWORD")
SEED_DEMO_USERS = _env("SEED_DEMO_USERS", "false").lower() in {"1", "true", "yes", "on"}
ADMIN_SESSION_HOURS = int(_env("ADMIN_SESSION_HOURS", "12"))
ADMIN_MAX_LOGIN_FAILURES = int(_env("ADMIN_MAX_LOGIN_FAILURES", "5"))
ADMIN_LOCK_MINUTES = int(_env("ADMIN_LOCK_MINUTES", "15"))

MULTIMODAL_API_KEY = _env("MULTIMODAL_API_KEY")
MULTIMODAL_BASE_URL = _env("MULTIMODAL_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MULTIMODAL_MODEL = _env("MULTIMODAL_MODEL", "gpt-4o-mini")
MULTIMODAL_TIMEOUT_SECONDS = int(_env("MULTIMODAL_TIMEOUT_SECONDS", "180"))
ALLOW_DEMO_REPORT = _env("ALLOW_DEMO_REPORT", "false").lower() in {"1", "true", "yes", "on"}

# 默认值不再放开全部来源；未显式配置时只允许公开站点自身。
CORS_ORIGINS = [
    item.strip()
    for item in _env("CORS_ORIGINS", PUBLIC_BASE_URL).split(",")
    if item.strip()
]
SHARE_DEFAULT_EXPIRES_DAYS = int(_env("SHARE_DEFAULT_EXPIRES_DAYS", "30"))
ENABLE_API_DOCS = _env("ENABLE_API_DOCS", "true").lower() in {"1", "true", "yes", "on"}
# 内部操作手册含后台截图与示例账号信息，生产环境默认不对公网提供。
ENABLE_MANUAL = _env("ENABLE_MANUAL", "false" if APP_ENV == "production" else "true").lower() in {"1", "true", "yes", "on"}


# 沙盘图与成绩单图片使用短期签名 URL，避免 /media 目录被公开枚举。
# 生产环境必须配置独立随机值；开发环境退化为本地固定值，重启后已发出的旧链接会失效。
_MEDIA_SECRET_CONFIGURED = bool(_env("MEDIA_SIGNING_SECRET") or COUNSELOR_TOKEN)
MEDIA_SIGNING_SECRET_CONFIGURED = _MEDIA_SECRET_CONFIGURED

MEDIA_SIGNING_SECRET = _env("MEDIA_SIGNING_SECRET") or COUNSELOR_TOKEN or "dev-media-signing-only"
MEDIA_SIGNED_URL_TTL_SECONDS = int(_env("MEDIA_SIGNED_URL_TTL_SECONDS", "604800"))



DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
