"""Engine, schema creation, and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "ratkitchen.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """Create the data directory, the schema, and the singleton settings row."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import app.models as models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(models.Setting, 1) is None:
            session.add(models.Setting(id=1))
            session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
