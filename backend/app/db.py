from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DATA_DIR


def _normalise_database_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        raw = url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = (DATA_DIR.parent / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    return url


class Base(DeclarativeBase):
    pass


DATABASE_URL_RESOLVED = _normalise_database_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if DATABASE_URL_RESOLVED.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL_RESOLVED, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _migrate_legacy_schema()


def _migrate_legacy_schema() -> None:
    """SQLite / PostgreSQL 通用的轻量迁移。

    create_all 不会给已存在的表补列。这里只做向后兼容的 ADD COLUMN，
    不删除、不重命名任何历史数据。
    """
    migrations = {
        "assessments": [
            ("school_name", "VARCHAR(120) DEFAULT ''"),
            ("class_name", "VARCHAR(80) DEFAULT ''"),
            ("seat_no", "VARCHAR(40) DEFAULT ''"),
            ("contact_phone", "VARCHAR(80) DEFAULT ''"),
            ("academic_scores_json", "TEXT DEFAULT '{}'"),
            ("self_image", "VARCHAR(120) DEFAULT ''"),
            ("self_image_note", "TEXT"),
            ("report_revision", "INTEGER DEFAULT 0"),
        ],
        "report_reviews": [
            ("ai_report_json", "TEXT"),
            ("draft_report_json", "TEXT"),
            ("draft_note", "TEXT DEFAULT ''"),
            ("draft_updated_at", "TIMESTAMP"),
            ("review_applied_at", "TIMESTAMP"),
        ],
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in migrations.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns:
                if name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
