import pytest

WEEKS = [
    "2026-06-01",
    "2026-06-08",
    "2026-06-15",
    "2026-06-22",
    "2026-06-29",
]


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


def finished_week(client, week, manual_names):
    """Create a plan with no meals, add manual items, and finalize its list."""
    plan = client.post("/api/plans", json={"week_start": week}).json()
    list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
    for name in manual_names:
        client.post(f"/api/lists/{list_id}/items", json={"custom_name": name})
    client.post(f"/api/lists/{list_id}/finalize")
    return list_id


def open_week(client, week):
    plan = client.post("/api/plans", json={"week_start": week}).json()
    return client.post(f"/api/plans/{plan['id']}/list").json()["id"]


def suggestions(client, list_id):
    return client.get(f"/api/lists/{list_id}/suggestions").json()


def test_an_item_bought_three_of_four_weeks_is_suggested(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[3], ["Bananas"])
    current = open_week(client, WEEKS[4])
    assert [s["name"] for s in suggestions(client, current)] == ["Coffee"]


def test_times_bought_is_reported(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[3], ["Coffee"])
    current = open_week(client, WEEKS[4])
    assert suggestions(client, current)[0]["times_bought"] == 4


def test_an_item_bought_twice_is_not_suggested(client):
    for week in WEEKS[:2]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[2], [])
    finished_week(client, WEEKS[3], [])
    current = open_week(client, WEEKS[4])
    assert suggestions(client, current) == []


def test_lists_older_than_the_window_do_not_count(client):
    # Three OLD weeks with Coffee...
    old_weeks = ["2026-05-04", "2026-05-11", "2026-05-18"]
    for week in old_weeks:
        finished_week(client, week, ["Coffee"])
    # ...then four MORE RECENT weeks without it. These push the coffee weeks
    # out of the HISTORY_WINDOW.
    recent_weeks = ["2026-05-25", "2026-06-01", "2026-06-08", "2026-06-15"]
    for week in recent_weeks:
        finished_week(client, week, [])
    current = open_week(client, "2026-06-22")
    assert [s["name"] for s in suggestions(client, current)] == []


def test_matching_is_case_and_whitespace_insensitive(client):
    finished_week(client, WEEKS[0], ["Coffee"])
    finished_week(client, WEEKS[1], ["  coffee "])
    finished_week(client, WEEKS[2], ["COFFEE"])
    current = open_week(client, WEEKS[3])
    assert len(suggestions(client, current)) == 1


def test_an_item_already_on_the_current_list_is_not_suggested(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    current = open_week(client, WEEKS[3])
    client.post(f"/api/lists/{current}/items", json={"custom_name": "coffee"})
    assert suggestions(client, current) == []


def test_recipe_items_are_never_suggested(client, onion):
    chili = client.post(
        "/api/recipes",
        json={
            "name": "Chili",
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}
            ],
        },
    ).json()
    for week in WEEKS[:3]:
        plan = client.post("/api/plans", json={"week_start": week}).json()
        client.post(
            f"/api/plans/{plan['id']}/meals",
            json={"day": 0, "slot": "dinner", "recipe_id": chili["id"], "kind": "cook"},
        )
        list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
        client.post(f"/api/lists/{list_id}/finalize")
    current = open_week(client, WEEKS[3])
    assert suggestions(client, current) == []


def test_ingredient_backed_manual_items_are_suggested_by_ingredient(client, onion):
    for week in WEEKS[:3]:
        plan = client.post("/api/plans", json={"week_start": week}).json()
        list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
        client.post(
            f"/api/lists/{list_id}/items",
            json={"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"},
        )
        client.post(f"/api/lists/{list_id}/finalize")
    current = open_week(client, WEEKS[3])
    result = suggestions(client, current)
    assert result[0]["ingredient_id"] == onion["id"]
    assert result[0]["name"] == "Onion"


def test_no_history_produces_no_suggestions(client):
    current = open_week(client, WEEKS[0])
    assert suggestions(client, current) == []
