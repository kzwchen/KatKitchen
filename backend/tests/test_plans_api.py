import pytest


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


@pytest.fixture
def chili(client, onion):
    return client.post(
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


@pytest.fixture
def plan(client):
    return client.post("/api/plans", json={"week_start": "2026-08-17"}).json()


def add_meal(client, plan_id, **overrides):
    payload = {"day": 0, "slot": "dinner", "recipe_id": None, "kind": "cook"}
    payload.update(overrides)
    return client.post(f"/api/plans/{plan_id}/meals", json=payload)


def test_create_plan_defaults_to_planning(client):
    response = client.post("/api/plans", json={"week_start": "2026-08-17"})
    assert response.status_code == 201
    assert response.json()["status"] == "planning"
    assert response.json()["meals"] == []


def test_create_plan_rejects_a_duplicate_week(client, plan):
    response = client.post("/api/plans", json={"week_start": "2026-08-17"})
    assert response.status_code == 409
    assert response.json()["code"] == "plan_exists"


def test_create_plan_rejects_a_week_start_that_is_not_monday(client):
    response = client.post("/api/plans", json={"week_start": "2026-08-19"})
    assert response.status_code == 422
    assert response.json()["code"] == "not_monday"


def test_cook_meal_defaults_servings_to_the_recipe_yield(client, plan, chili):
    response = add_meal(client, plan["id"], recipe_id=chili["id"])
    assert response.status_code == 201
    meal = response.json()
    assert meal["servings_to_make"] == 4
    assert meal["recipe_name"] == "Chili"


def test_cook_meal_defaults_servings_eaten_to_household_size(client, plan, chili):
    client.patch("/api/settings", json={"household_size": 3})
    meal = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    assert meal["servings_eaten"] == 3


def test_a_slot_can_hold_only_one_meal(client, plan, chili):
    add_meal(client, plan["id"], recipe_id=chili["id"])
    response = add_meal(client, plan["id"], recipe_id=chili["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "slot_taken"


def test_leftovers_must_reference_a_source(client, plan, chili):
    response = add_meal(
        client, plan["id"], day=1, slot="lunch", recipe_id=chili["id"], kind="leftovers"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_need_source"


def test_leftovers_accept_an_earlier_cook_of_the_same_recipe(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 201
    assert response.json()["servings_to_make"] is None


def test_leftovers_are_rejected_before_their_source(client, plan, chili):
    cook = add_meal(client, plan["id"], day=3, recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_before_source"


def test_leftovers_are_rejected_for_a_different_recipe(client, plan, chili, onion):
    soup = client.post(
        "/api/recipes",
        json={
            "name": "Soup",
            "serves": 2,
            "instructions": "Boil.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"}
            ],
        },
    ).json()
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=soup["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_recipe_mismatch"


def test_leftovers_are_rejected_when_the_source_is_itself_leftovers(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    first = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    ).json()
    response = add_meal(
        client,
        plan["id"],
        day=2,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=first["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_source_not_cook"


def test_no_warning_when_the_batch_covers_every_serving(client, plan, chili):
    # serves 4, household 2: cook eats 2, one leftover slot eats 2. Exactly 4.
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert client.get(f"/api/plans/{plan['id']}").json()["warnings"] == []


def test_warning_when_leftovers_outrun_the_batch(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    for day, slot in ((1, "lunch"), (2, "lunch")):
        add_meal(
            client,
            plan["id"],
            day=day,
            slot=slot,
            recipe_id=chili["id"],
            kind="leftovers",
            source_meal_id=cook["id"],
        )
    warnings = client.get(f"/api/plans/{plan['id']}").json()["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["meal_id"] == cook["id"]
    assert "6" in warnings[0]["message"] and "4" in warnings[0]["message"]


def test_patching_servings_to_make_clears_the_warning(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    for day, slot in ((1, "lunch"), (2, "lunch")):
        add_meal(
            client,
            plan["id"],
            day=day,
            slot=slot,
            recipe_id=chili["id"],
            kind="leftovers",
            source_meal_id=cook["id"],
        )
    client.patch(f"/api/meals/{cook['id']}", json={"servings_to_make": 6})
    assert client.get(f"/api/plans/{plan['id']}").json()["warnings"] == []


def test_deleting_a_cook_meal_with_leftovers_is_refused(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    response = client.delete(f"/api/meals/{cook['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "meal_has_leftovers"


def test_deleting_a_leftover_meal_succeeds(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    leftover = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    ).json()
    assert client.delete(f"/api/meals/{leftover['id']}").status_code == 204
    assert len(client.get(f"/api/plans/{plan['id']}").json()["meals"]) == 1


def test_plan_list_is_newest_first(client):
    client.post("/api/plans", json={"week_start": "2026-08-10"})
    client.post("/api/plans", json={"week_start": "2026-08-17"})
    weeks = [p["week_start"] for p in client.get("/api/plans").json()]
    assert weeks == ["2026-08-17", "2026-08-10"]


def test_deleting_a_plan_removes_its_meals(client, plan, chili):
    add_meal(client, plan["id"], recipe_id=chili["id"])
    assert client.delete(f"/api/plans/{plan['id']}").status_code == 204
    assert client.get(f"/api/plans/{plan['id']}").status_code == 404
