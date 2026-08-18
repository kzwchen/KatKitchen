"""Whole-API error contract: every error response is {"detail": str, "code": str}.

Covers the two failure paths FastAPI generates itself (pydantic validation,
and Starlette's own 404/405) plus a regression guard for the pre-existing
AppError contract that tasks 5 and 6 depend on.
"""


def test_pydantic_validation_error_has_string_detail_and_validation_error_code(client):
    response = client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "not-a-real-category", "unit": "count"},
    )
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "validation_error"
    # The message should still be readable/useful, not just discarded.
    assert "category" in body["detail"]


def test_unmatched_route_returns_not_found_with_both_keys(client):
    response = client.get("/api/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "not_found"


def test_wrong_method_on_existing_path_returns_method_not_allowed(client):
    # /api/health only supports GET.
    response = client.post("/api/health")
    assert response.status_code == 405
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "method_not_allowed"


def test_app_error_regression_guard_still_has_its_specific_code(client):
    payload = {"name": "Onion", "category": "produce", "unit": "count", "is_staple": False}
    first = client.post("/api/ingredients", json=payload)
    assert first.status_code == 201
    second = client.post("/api/ingredients", json={**payload, "name": "onion"})
    assert second.status_code == 409
    body = second.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "ingredient_exists"
