"""The test suite must be hermetic: no test may open the real on-disk database
at <repo>/data/ratkitchen.db.

This check is deliberately NON-DESTRUCTIVE. An earlier version deleted the
real database at collection time to guarantee a clean slate, which meant
running `pytest` silently destroyed the developer's actual recipe data.

It is also deliberately not a filesystem check. Fingerprinting the database
file (size/mtime, or the presence of SQLite's journal sidecars) does NOT
discriminate: `init_db()` calls `create_all(checkfirst=True)`, so against an
existing, fully-migrated database it emits no DDL and leaves the file byte
identical. A filesystem assertion passes whether or not the leak is present,
which is no test at all.

What actually discriminates is watching the production engine itself. A
`connect` listener is attached to `app.db.engine` at collection time —
before pytest runs any test — and every connection to it is recorded for the
whole session. The production engine is a distinct object from the in-memory
engine the `client` fixture wires in via the `get_session` override, so a
single recorded connect means some test reached the real database.
"""

from pathlib import Path

from sqlalchemy import event

import app.db

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "ratkitchen.db"

# Every connection opened against the real, on-disk engine during this
# session, as formatted stack traces. Populated by the listener below.
REAL_ENGINE_CONNECTIONS: list[str] = []


@event.listens_for(app.db.engine, "connect")
def _record_real_engine_connection(_dbapi_connection, _record) -> None:
    import traceback

    REAL_ENGINE_CONNECTIONS.append("".join(traceback.format_stack()))


def test_using_the_client_fixture_does_not_open_the_real_database(client):
    response = client.post(
        "/api/ingredients",
        json={"name": "isolation probe", "category": "produce", "unit": "count"},
    )
    assert response.status_code == 201, response.text

    assert not REAL_ENGINE_CONNECTIONS, (
        f"{len(REAL_ENGINE_CONNECTIONS)} connection(s) were opened against the "
        f"real database at {DB_PATH} during this test session. The client "
        "fixture must patch app.main.init_db and override get_session so that "
        "no request or lifespan event touches the production engine.\n\n"
        "First offending stack:\n" + REAL_ENGINE_CONNECTIONS[0]
    )
