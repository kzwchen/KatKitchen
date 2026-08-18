import pytest

PLANS_LAND_IN_TASK_6 = pytest.mark.xfail(
    reason="plans router lands in Task 6", strict=True
)


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


@PLANS_LAND_IN_TASK_6
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
