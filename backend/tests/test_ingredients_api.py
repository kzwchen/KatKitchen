def create_ingredient(client, **overrides):
    payload = {"name": "Onion", "category": "produce", "unit": "count", "is_staple": False}
    payload.update(overrides)
    return client.post("/api/ingredients", json=payload)


def add_recipe(client, ingredient_id, name="Chili", quantity=2, display_unit="count"):
    return client.post(
        "/api/recipes",
        json={
            "name": name,
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity": quantity,
                    "display_unit": display_unit,
                }
            ],
        },
    )


def test_create_returns_the_ingredient(client):
    response = create_ingredient(client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Onion"
    assert body["unit"] == "count"
    assert body["usage_count"] == 0


def test_create_rejects_a_duplicate_name_case_insensitively(client):
    create_ingredient(client)
    response = create_ingredient(client, name="onion")
    assert response.status_code == 409
    assert response.json()["code"] == "ingredient_exists"


def test_create_defaults_seasonings_to_staple(client):
    payload = {"name": "Cumin", "category": "seasoning", "unit": "ml"}
    response = client.post("/api/ingredients", json=payload)
    assert response.json()["is_staple"] is True


def test_create_rejects_a_unit_that_is_not_canonical(client):
    response = create_ingredient(client, name="Flour", category="dry_goods", unit="kg")
    assert response.status_code == 422


def test_list_supports_search(client):
    create_ingredient(client, name="Onion")
    create_ingredient(client, name="Chicken thigh", category="meat_seafood", unit="g")
    results = client.get("/api/ingredients", params={"q": "chick"}).json()
    assert [i["name"] for i in results] == ["Chicken thigh"]


def test_list_is_alphabetical(client):
    create_ingredient(client, name="Pasta", category="dry_goods", unit="g")
    create_ingredient(client, name="Apple")
    results = client.get("/api/ingredients").json()
    assert [i["name"] for i in results] == ["Apple", "Pasta"]


def test_patch_updates_name_and_staple_flag(client):
    ingredient_id = create_ingredient(client).json()["id"]
    response = client.patch(
        f"/api/ingredients/{ingredient_id}", json={"name": "Red onion", "is_staple": True}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Red onion"
    assert response.json()["is_staple"] is True


def test_delete_removes_an_unused_ingredient(client):
    ingredient_id = create_ingredient(client).json()["id"]
    assert client.delete(f"/api/ingredients/{ingredient_id}").status_code == 204
    assert client.get(f"/api/ingredients/{ingredient_id}").status_code == 404


def test_changing_unit_is_allowed_while_unused(client):
    ingredient_id = create_ingredient(
        client, name="Spinach", category="produce", unit="count"
    ).json()["id"]
    response = client.patch(f"/api/ingredients/{ingredient_id}", json={"unit": "g"})
    assert response.status_code == 200
    assert response.json()["unit"] == "g"


def test_delete_is_refused_when_a_recipe_uses_it(client):
    ingredient_id = create_ingredient(client).json()["id"]
    add_recipe(client, ingredient_id)
    response = client.delete(f"/api/ingredients/{ingredient_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "ingredient_in_use"
    assert "Chili" in response.json()["detail"]


def test_delete_is_refused_when_a_shopping_list_item_references_it(client):
    # Investigation: ShoppingListItem.ingredient_id is a real FK and
    # PRAGMA foreign_keys=ON is enforced, so deleting an ingredient that a
    # shopping-list item still points at raises a raw IntegrityError deep in
    # SQLAlchemy/sqlite - not a dangling reference, and (before this fix)
    # not a clean 409 either: it surfaces as an unhandled 500.
    ingredient_id = create_ingredient(client).json()["id"]
    plan = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()
    list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
    client.post(
        f"/api/lists/{list_id}/items",
        json={"ingredient_id": ingredient_id, "quantity": 1, "display_unit": "count"},
    )
    response = client.delete(f"/api/ingredients/{ingredient_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "ingredient_in_use"
    # The ingredient must genuinely survive - not a dangling reference.
    assert client.get(f"/api/ingredients/{ingredient_id}").status_code == 200


def test_changing_unit_is_refused_when_a_recipe_uses_it(client):
    ingredient_id = create_ingredient(
        client, name="Flour", category="dry_goods", unit="g"
    ).json()["id"]
    add_recipe(client, ingredient_id, name="Bread", quantity=500, display_unit="g")
    response = client.patch(f"/api/ingredients/{ingredient_id}", json={"unit": "ml"})
    assert response.status_code == 409
    assert response.json()["code"] == "unit_locked"


def test_usage_count_reflects_recipes(client):
    ingredient_id = create_ingredient(client).json()["id"]
    add_recipe(client, ingredient_id)
    assert client.get(f"/api/ingredients/{ingredient_id}").json()["usage_count"] == 1


def test_settings_default_and_patch(client):
    assert client.get("/api/settings").json()["household_size"] == 2
    response = client.patch("/api/settings", json={"household_size": 4})
    assert response.json()["household_size"] == 4
    assert client.get("/api/settings").json()["household_size"] == 4
