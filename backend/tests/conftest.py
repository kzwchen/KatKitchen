import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import for side effect: registers every table on SQLModel.metadata.
    import app.models  # noqa: F401

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    SQLModel.metadata.create_all(engine)

    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine, monkeypatch):
    from app.db import get_session
    from app.main import app

    def override_get_session():
        with Session(engine) as session:
            yield session

    # The app's lifespan calls app.db.init_db() on startup, which is bound
    # to the real, on-disk engine (a separate module-level object from the
    # in-memory `engine` fixture above, which is only wired in via the
    # get_session override for request handling). Left alone, entering the
    # TestClient context below would run that real init_db() and write to
    # the real <repo>/data/ratkitchen.db file. Production startup under
    # uvicorn is unaffected: this patches only app.main's reference to
    # init_db, and only for the lifetime of this fixture.
    monkeypatch.setattr("app.main.init_db", lambda: None)

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
