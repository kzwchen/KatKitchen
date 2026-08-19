import pytest
from sqlmodel import select

from app.models import MealKind, PlannedMeal


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


@pytest.fixture
def chicken(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Chicken thigh", "category": "meat_seafood", "unit": "g"},
    ).json()


def make_recipe(client, lines, **overrides):
    payload = {
        "name": "Chili",
        "serves": 4,
        "instructions": "Simmer.",
        "source_url": None,
        "notes": None,
        "lines": lines,
    }
    payload.update(overrides)
    return client.post("/api/recipes", json=payload)


def test_create_stores_lines_in_canonical_units(client, chicken):
    response = make_recipe(
        client, [{"ingredient_id": chicken["id"], "quantity": 1, "display_unit": "kg"}]
    )
    assert response.status_code == 201
    line = response.json()["lines"][0]
    assert line["quantity"] == 1000.0
    assert line["display_unit"] == "kg"
    assert line["display_quantity"] == 1.0
    assert line["ingredient_name"] == "Chicken thigh"


def test_create_rejects_a_unit_outside_the_ingredient_family(client, onion):
    response = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 200, "display_unit": "g"}]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unit_mismatch"


def test_create_rejects_an_unknown_ingredient(client):
    response = make_recipe(
        client, [{"ingredient_id": 999, "quantity": 1, "display_unit": "count"}]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ingredient_not_found"


def test_create_rejects_a_duplicate_ingredient_line(client, onion):
    response = make_recipe(
        client,
        [
            {"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"},
            {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"},
        ],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "duplicate_line"


def test_lines_keep_their_order(client, onion, chicken):
    response = make_recipe(
        client,
        [
            {"ingredient_id": chicken["id"], "quantity": 500, "display_unit": "g"},
            {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"},
        ],
    )
    names = [line["ingredient_name"] for line in response.json()["lines"]]
    assert names == ["Chicken thigh", "Onion"]


def test_patch_replaces_the_line_set_wholesale(client, onion, chicken):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    response = client.patch(
        f"/api/recipes/{recipe_id}",
        json={
            "lines": [
                {"ingredient_id": chicken["id"], "quantity": 300, "display_unit": "g"}
            ]
        },
    )
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["ingredient_name"] == "Chicken thigh"


def test_patch_without_lines_leaves_them_alone(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    response = client.patch(f"/api/recipes/{recipe_id}", json={"serves": 8})
    assert response.json()["serves"] == 8
    assert len(response.json()["lines"]) == 1


def test_list_returns_summaries_and_supports_search(client, onion):
    line = [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    make_recipe(client, line)
    make_recipe(client, line, name="Soup")
    results = client.get("/api/recipes", params={"q": "chi"}).json()
    assert [r["name"] for r in results] == ["Chili"]
    assert results[0]["line_count"] == 1


def test_delete_removes_an_unplanned_recipe(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404


def test_delete_is_refused_while_an_active_plan_uses_it(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    plan_id = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()["id"]
    client.post(
        f"/api/plans/{plan_id}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": recipe_id, "kind": "cook"},
    )
    response = client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "recipe_in_use"
    assert "2026-08-17" in response.json()["detail"]


def cook_a_week(client, recipe_id, week_start, *, leftovers=False):
    """Plan `recipe_id` for a week, generate its list, and mark it done.

    Returns (plan_id, list_id) for the finished week.
    """
    plan_id = client.post("/api/plans", json={"week_start": week_start}).json()["id"]
    cook = client.post(
        f"/api/plans/{plan_id}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": recipe_id, "kind": "cook"},
    )
    assert cook.status_code == 201, cook.text
    if leftovers:
        response = client.post(
            f"/api/plans/{plan_id}/meals",
            json={
                "day": 1,
                "slot": "lunch",
                "recipe_id": recipe_id,
                "kind": "leftovers",
                "source_meal_id": cook.json()["id"],
            },
        )
        assert response.status_code == 201, response.text
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    finalized = client.post(f"/api/lists/{list_id}/finalize")
    assert finalized.status_code == 200, finalized.text
    assert client.get(f"/api/plans/{plan_id}").json()["status"] == "done"
    return plan_id, list_id


def test_delete_drops_the_planned_slots_of_a_finished_week(client, onion):
    """The normal path: every recipe the user actually cooks ends up here."""
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    plan_id, _ = cook_a_week(client, recipe_id, "2026-08-17")

    response = client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 204, response.text
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404
    assert client.get(f"/api/plans/{plan_id}").json()["meals"] == []


def test_delete_drops_a_finished_cook_slot_and_the_leftovers_that_eat_from_it(
    client, onion
):
    """The self-referencing FK: the leftovers row must go before its source."""
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    plan_id, _ = cook_a_week(client, recipe_id, "2026-08-17", leftovers=True)
    assert len(client.get(f"/api/plans/{plan_id}").json()["meals"]) == 2

    response = client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 204, response.text
    assert client.get(f"/api/plans/{plan_id}").json()["meals"] == []


def test_delete_drops_a_finished_leftovers_slot_of_another_recipe(
    client, session, onion
):
    """A leftovers row whose own recipe_id differs from its source's.

    The API cannot produce this -- `_validate_leftovers` requires the two to
    match, and `update_meal` refuses to re-point a cook meal that has
    leftovers -- so it is built directly against the session. It is the one
    shape the recipe_id query cannot see, and it must still not strand a row
    pointing at a deleted cook meal.
    """
    line = [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    doomed = make_recipe(client, line).json()["id"]
    other = make_recipe(client, line, name="Soup").json()["id"]
    plan_id, _ = cook_a_week(client, doomed, "2026-08-17", leftovers=True)

    leftovers = session.exec(
        select(PlannedMeal).where(PlannedMeal.kind == MealKind.LEFTOVERS)
    ).one()
    leftovers.recipe_id = other
    session.add(leftovers)
    session.commit()
    leftovers_id = leftovers.id

    response = client.delete(f"/api/recipes/{doomed}")
    assert response.status_code == 204, response.text
    assert client.get(f"/api/plans/{plan_id}").json()["meals"] == []
    session.expire_all()
    assert session.get(PlannedMeal, leftovers_id) is None


def test_delete_leaves_an_archived_shopping_list_untouched(client, onion):
    """`contributions` snapshots recipe_name, so history survives the delete."""
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    _, list_id = cook_a_week(client, recipe_id, "2026-08-17")
    before = client.get(f"/api/lists/{list_id}").json()
    assert before["items"][0]["contributions"] == [
        {"recipe_id": recipe_id, "recipe_name": "Chili", "quantity": 2.0}
    ]

    history_before = client.get("/api/lists").json()
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/lists/{list_id}").json() == before
    assert client.get("/api/lists").json() == history_before


def test_delete_refusal_names_only_the_weeks_that_are_still_open(client, onion):
    """The 409 message is user-facing: a finished week is not a reason to refuse."""
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    cook_a_week(client, recipe_id, "2026-08-10")
    # Created newest-first, so the message has to sort rather than echo
    # whatever order the join happened to return.
    for week in ("2026-08-24", "2026-08-17"):
        open_plan = client.post("/api/plans", json={"week_start": week}).json()["id"]
        client.post(
            f"/api/plans/{open_plan}/meals",
            json={"day": 0, "slot": "dinner", "recipe_id": recipe_id, "kind": "cook"},
        )

    response = client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "recipe_in_use"
    assert response.json()["detail"] == (
        "Can't delete Chili: planned for 2026-08-17, 2026-08-24"
    )
