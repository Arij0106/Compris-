"""Connexion SQLAlchemy (SQLite par défaut, PostgreSQL via DATABASE_URL)."""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

db_url = settings.database_url
# Si l'URL pointe vers le conteneur (/app/...) alors qu'on exécute en local
if db_url.startswith("sqlite:////app/") and not Path("/app").exists():
    db_url = f"sqlite:///{settings.storage_dir / 'app.db'}"

_is_sqlite = db_url.startswith("sqlite")
engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (enregistre les tables)

    Base.metadata.create_all(bind=engine)
