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
