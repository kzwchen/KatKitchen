"""The test suite must be hermetic: using the `client` fixture must never
create the real on-disk database at <repo>/data/ratkitchen.db.

The file is removed (if present) at collection time, before any test in the
session executes. That guarantees a clean slate: if the fix is missing, the
lifespan's real init_db() call will recreate the file the very first time
any test anywhere in the suite uses the `client` fixture, and this test
will observe that.
"""

from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "ratkitchen.db"

if DB_PATH.exists():
    DB_PATH.unlink()


def test_using_the_client_fixture_does_not_create_the_real_database(client):
    client.get("/api/health")
    client.get("/api/settings")
    assert not DB_PATH.exists(), (
        "the real database file was created by the test suite; the client "
        "fixture must not run the production lifespan's init_db()"
    )
