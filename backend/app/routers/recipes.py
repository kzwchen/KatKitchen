from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import (
    Ingredient,
    MealPlan,
    PlanStatus,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
)
from app.schemas import (
    RecipeIn,
    RecipeLineIn,
    RecipeLineOut,
    RecipeOut,
    RecipePatch,
    RecipeSummary,
)
from app.services.units import CONVERSIONS, UnitError, to_canonical

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _get_or_404(session: Session, recipe_id: int) -> Recipe:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise AppError(404, "recipe_not_found", f"No recipe {recipe_id}")
    return recipe


def _validate_lines(
    session: Session, lines: list[RecipeLineIn]
) -> list[tuple[RecipeLineIn, float]]:
    """Resolve each line's ingredient and convert its quantity to canonical."""
    seen: set[int] = set()
    resolved: list[tuple[RecipeLineIn, float]] = []
    for line in lines:
        if line.ingredient_id in seen:
            raise AppError(
                422,
                "duplicate_line",
                f"Ingredient {line.ingredient_id} appears more than once",
            )
        seen.add(line.ingredient_id)

        ingredient = session.get(Ingredient, line.ingredient_id)
        if ingredient is None:
            raise AppError(
                422, "ingredient_not_found", f"No ingredient {line.ingredient_id}"
            )
        try:
            canonical = to_canonical(
                line.quantity, line.display_unit, ingredient.unit.value
            )
        except UnitError as exc:
            raise AppError(422, "unit_mismatch", str(exc)) from None
        resolved.append((line, canonical))
    return resolved


def _replace_lines(session: Session, recipe: Recipe, lines: list[RecipeLineIn]) -> None:
    resolved = _validate_lines(session, lines)
    recipe.lines.clear()
    session.flush()
    for position, (line, canonical) in enumerate(resolved):
        recipe.lines.append(
            RecipeIngredient(
                ingredient_id=line.ingredient_id,
                quantity=canonical,
                display_unit=line.display_unit,
                prep_note=line.prep_note,
                position=position,
            )
        )


def _line_out(session: Session, line: RecipeIngredient) -> RecipeLineOut:
    ingredient = session.get(Ingredient, line.ingredient_id)
    factor = CONVERSIONS[line.display_unit][1]
    return RecipeLineOut(
        id=line.id,
        ingredient_id=line.ingredient_id,
        ingredient_name=ingredient.name,
        ingredient_unit=ingredient.unit,
        category=ingredient.category,
        quantity=line.quantity,
        display_quantity=round(line.quantity / factor, 4),
        display_unit=line.display_unit,
        prep_note=line.prep_note,
        position=line.position,
    )


def _to_out(session: Session, recipe: Recipe) -> RecipeOut:
    return RecipeOut(
        id=recipe.id,
        name=recipe.name,
        serves=recipe.serves,
        instructions=recipe.instructions,
        source_url=recipe.source_url,
        notes=recipe.notes,
        lines=[_line_out(session, line) for line in recipe.lines],
    )


@router.get("", response_model=list[RecipeSummary])
def list_recipes(
    q: str | None = Query(default=None), session: Session = Depends(get_session)
) -> list[RecipeSummary]:
    statement = select(Recipe)
    if q:
        statement = statement.where(Recipe.name.ilike(f"%{q}%"))
    recipes = session.exec(statement.order_by(func.lower(Recipe.name))).all()
    return [
        RecipeSummary(id=r.id, name=r.name, serves=r.serves, line_count=len(r.lines))
        for r in recipes
    ]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeIn, session: Session = Depends(get_session)
) -> RecipeOut:
    recipe = Recipe(
        name=payload.name.strip(),
        serves=payload.serves,
        instructions=payload.instructions,
        source_url=payload.source_url,
        notes=payload.notes,
    )
    session.add(recipe)
    _replace_lines(session, recipe, payload.lines)
    session.commit()
    session.refresh(recipe)
    return _to_out(session, recipe)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, session: Session = Depends(get_session)) -> RecipeOut:
    return _to_out(session, _get_or_404(session, recipe_id))


@router.patch("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int, payload: RecipePatch, session: Session = Depends(get_session)
) -> RecipeOut:
    recipe = _get_or_404(session, recipe_id)
    changes = payload.model_dump(exclude_unset=True)
    lines = changes.pop("lines", None)

    for key, value in changes.items():
        setattr(recipe, key, value)
    if lines is not None:
        _replace_lines(session, recipe, [RecipeLineIn(**line) for line in lines])
    recipe.updated_at = datetime.now(timezone.utc)

    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return _to_out(session, recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, session: Session = Depends(get_session)) -> Response:
    recipe = _get_or_404(session, recipe_id)
    weeks = list(
        session.exec(
            select(MealPlan.week_start)
            .join(PlannedMeal, PlannedMeal.plan_id == MealPlan.id)
            .where(PlannedMeal.recipe_id == recipe_id)
            .where(MealPlan.status != PlanStatus.DONE)
            .distinct()
        )
    )
    if weeks:
        listed = ", ".join(str(week) for week in weeks)
        raise AppError(
            409, "recipe_in_use", f"Can't delete {recipe.name}: planned for {listed}"
        )
    session.delete(recipe)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
