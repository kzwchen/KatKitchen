import pytest


@pytest.fixture
def world(client):
    onion = client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()
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
    plan = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()
    client.post(
        f"/api/plans/{plan['id']}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": chili["id"], "kind": "cook"},
    )
    return {"onion": onion, "chili": chili, "plan": plan}


def test_get_before_generating_is_404(client, world):
    response = client.get(f"/api/plans/{world['plan']['id']}/list")
    assert response.status_code == 404
    assert response.json()["code"] == "list_not_found"


def test_post_generates_the_list_and_moves_the_plan_to_shopping(client, world):
    response = client.post(f"/api/plans/{world['plan']['id']}/list")
    assert response.status_code == 201
    body = response.json()
    assert body["week_start"] == "2026-08-17"
    assert [i["name"] for i in body["items"]] == ["Onion"]
    assert body["items"][0]["display_quantity"] == 2.0
    assert body["items"][0]["category"] == "produce"
    plan = client.get(f"/api/plans/{world['plan']['id']}").json()
    assert plan["status"] == "shopping"


def test_contributions_explain_each_line(client, world):
    body = client.post(f"/api/plans/{world['plan']['id']}/list").json()
    assert body["items"][0]["contributions"][0]["recipe_name"] == "Chili"


def test_manual_items_can_be_added_and_checked(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    added = client.post(
        f"/api/lists/{list_id}/items", json={"custom_name": "Paper towels"}
    )
    assert added.status_code == 201
    assert added.json()["source"] == "manual"

    item_id = added.json()["id"]
    patched = client.patch(
        f"/api/lists/{list_id}/items/{item_id}", json={"checked": True}
    )
    assert patched.json()["checked"] is True


def test_patching_display_unit_alone_keeps_the_display_pair_consistent(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    # Onion's canonical unit is "count", so add a gram-based item instead so
    # there is a real promotion threshold (1000 g -> kg) to exercise.
    flour = client.post(
        "/api/ingredients",
        json={"name": "Flour", "category": "dry_goods", "unit": "g"},
    ).json()
    added = client.post(
        f"/api/lists/{list_id}/items",
        json={"ingredient_id": flour["id"], "quantity": 1500, "display_unit": "g"},
    ).json()
    # add_item promotes this to kg via format_display.
    assert added["display_quantity"] == 1.5
    assert added["display_unit"] == "kg"
    item_id = added["id"]

    # PATCH display_unit alone (no quantity in the payload).
    patched = client.patch(
        f"/api/lists/{list_id}/items/{item_id}", json={"display_unit": "g"}
    ).json()
    # The underlying canonical amount (1500 g) hasn't changed, so the
    # recomputed display pair must still describe 1500 g consistently -
    # here that's (1.5, "kg") again, exactly like add_item would produce.
    # The bug this guards against is display_quantity staying stale (1.5)
    # while display_unit flips to the raw requested "g", which would silently
    # misrepresent the amount as 1.5 g instead of 1500 g.
    assert patched["quantity"] == 1500
    assert patched["display_quantity"] == 1.5
    assert patched["display_unit"] == "kg"


def test_a_manual_item_needs_a_name_or_an_ingredient(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    response = client.post(f"/api/lists/{list_id}/items", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "item_needs_name"


def test_manual_items_can_be_deleted(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    item_id = client.post(
        f"/api/lists/{list_id}/items", json={"custom_name": "Coffee"}
    ).json()["id"]
    assert client.delete(f"/api/lists/{list_id}/items/{item_id}").status_code == 204
    names = [i["name"] for i in client.get(f"/api/lists/{list_id}").json()["items"]]
    assert "Coffee" not in names


def test_regenerating_after_a_plan_change_updates_quantities(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    meal_id = client.get(f"/api/plans/{plan_id}").json()["meals"][0]["id"]
    client.patch(f"/api/meals/{meal_id}", json={"servings_to_make": 8})

    body = client.post(f"/api/plans/{plan_id}/list").json()
    assert body["id"] == list_id
    assert body["items"][0]["display_quantity"] == 4.0


def test_finalize_marks_the_list_and_the_plan_done(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    response = client.post(f"/api/lists/{list_id}/finalize")
    assert response.status_code == 200
    assert response.json()["finalized_at"] is not None
    assert client.get(f"/api/plans/{plan_id}").json()["status"] == "done"


def test_items_are_ordered_by_section_then_store_walk_category_then_name(client):
    # One buy-section ingredient per store-walk category, plus a seasoning
    # staple (lands in staple_check) and a free-text manual item (no
    # category at all). This pins the full _sorted_items contract: buy
    # before staple_check, categories in CATEGORY_ORDER, and a category-less
    # item sorting deterministically without blowing up the sort.
    ingredients = {}
    for name, category, unit, is_staple in [
        ("Zucchini", "produce", "count", False),
        ("Bagel", "bakery", "count", False),
        ("Chicken", "meat_seafood", "g", False),
        ("Milk", "dairy", "ml", False),
        ("Peas", "frozen", "g", False),
        ("Rice", "dry_goods", "g", False),
        ("Pepper", "seasoning", "ml", False),
        ("Gadget", "other", "count", False),
        ("Cumin", "seasoning", "ml", True),
    ]:
        ingredients[name] = client.post(
            "/api/ingredients",
            json={
                "name": name,
                "category": category,
                "unit": unit,
                "is_staple": is_staple,
            },
        ).json()

    lines = [
        {
            "ingredient_id": ingredient["id"],
            "quantity": 1,
            "display_unit": ingredient["unit"],
        }
        for ingredient in ingredients.values()
    ]
    recipe = client.post(
        "/api/recipes",
        json={"name": "Feast", "serves": 1, "instructions": "Cook.", "lines": lines},
    ).json()
    plan = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()
    client.post(
        f"/api/plans/{plan['id']}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": recipe["id"], "kind": "cook"},
    )
    list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"custom_name": "Batteries"})

    body = client.get(f"/api/lists/{list_id}").json()
    assert [i["name"] for i in body["items"]] == [
        "Zucchini",
        "Bagel",
        "Chicken",
        "Milk",
        "Peas",
        "Rice",
        "Pepper",
        "Gadget",
        "Batteries",
        "Cumin",
    ]
    sections = {i["name"]: i["section"] for i in body["items"]}
    assert sections["Cumin"] == "staple_check"
    assert all(
        sections[name] == "buy"
        for name in [
            "Zucchini", "Bagel", "Chicken", "Milk", "Peas", "Rice", "Pepper",
            "Gadget", "Batteries",
        ]
    )


def test_regenerating_a_done_plan_does_not_drag_it_back_to_shopping(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    client.post(f"/api/lists/{list_id}/finalize")
    assert client.get(f"/api/plans/{plan_id}").json()["status"] == "done"

    response = client.post(f"/api/plans/{plan_id}/list")
    assert response.status_code == 201
    assert client.get(f"/api/plans/{plan_id}").json()["status"] == "done"


def test_history_lists_only_finalized_lists(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    assert client.get("/api/lists").json() == []
    client.post(f"/api/lists/{list_id}/finalize")
    history = client.get("/api/lists").json()
    assert len(history) == 1
    assert history[0]["week_start"] == "2026-08-17"
    assert history[0]["item_count"] == 1
    assert history[0]["checked_count"] == 0
