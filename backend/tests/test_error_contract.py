"""Whole-API error contract: every error response is {"detail": str, "code": str}.

Covers the two failure paths FastAPI generates itself (pydantic validation,
and Starlette's own 404/405) plus a regression guard for the pre-existing
AppError contract that tasks 5 and 6 depend on.
"""

import json


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


def test_explicit_null_on_a_non_nullable_ingredient_field_keeps_the_envelope(client):
    # `exclude_unset` drops absent keys, but an explicit null IS set, so None
    # reached a NOT NULL column and SQLite's IntegrityError escaped as a bare
    # 500 with no `code` at all.
    ingredient = client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()
    response = client.patch(
        f"/api/ingredients/{ingredient['id']}", json={"is_staple": None}
    )
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "null_not_allowed"
    assert set(body) == {"detail", "code"}


def test_explicit_null_on_a_non_nullable_recipe_field_keeps_the_envelope(client):
    recipe = client.post(
        "/api/recipes",
        json={"name": "Chili", "serves": 4, "instructions": "Simmer.", "lines": []},
    ).json()
    response = client.patch(f"/api/recipes/{recipe['id']}", json={"instructions": None})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "null_not_allowed"
    assert set(body) == {"detail", "code"}


def test_a_non_null_integrity_error_is_a_conflict_in_the_same_envelope():
    # The handler must also cover the constraint kinds no route guard can
    # fully prevent -- e.g. add_meal's SELECT-then-INSERT slot check, where a
    # concurrent duplicate trips uq_plan_slot after the check has passed.
    # Driven directly because that race is not reproducible single-threaded.
    import asyncio

    import sqlite3

    from sqlalchemy.exc import IntegrityError

    from app.errors import integrity_error_handler

    orig = sqlite3.IntegrityError("UNIQUE constraint failed: plannedmeal.plan_id")
    orig.sqlite_errorname = "SQLITE_CONSTRAINT_UNIQUE"
    exc = IntegrityError("INSERT INTO plannedmeal ...", {}, orig)

    response = asyncio.run(integrity_error_handler(None, exc))
    assert response.status_code == 409
    body = json.loads(response.body)
    assert isinstance(body["detail"], str)
    assert body["code"] == "constraint_violation"
    assert set(body) == {"detail", "code"}


def test_app_error_regression_guard_still_has_its_specific_code(client):
    payload = {"name": "Onion", "category": "produce", "unit": "count", "is_staple": False}
    first = client.post("/api/ingredients", json=payload)
    assert first.status_code == 201
    second = client.post("/api/ingredients", json={**payload, "name": "onion"})
    assert second.status_code == 409
    body = second.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "ingredient_exists"
