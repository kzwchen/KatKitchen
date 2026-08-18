from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import Ingredient, Recipe, RecipeIngredient, ShoppingListItem
from app.schemas import IngredientIn, IngredientOut, IngredientPatch

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


def _usage_count(session: Session, ingredient_id: int) -> int:
    return session.exec(
        select(func.count(RecipeIngredient.id)).where(
            RecipeIngredient.ingredient_id == ingredient_id
        )
    ).one()


def _to_out(session: Session, ingredient: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=ingredient.id,
        name=ingredient.name,
        category=ingredient.category,
        unit=ingredient.unit,
        is_staple=ingredient.is_staple,
        usage_count=_usage_count(session, ingredient.id),
    )


def _get_or_404(session: Session, ingredient_id: int) -> Ingredient:
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise AppError(404, "ingredient_not_found", f"No ingredient {ingredient_id}")
    return ingredient


def _find_by_name(session: Session, name: str) -> Ingredient | None:
    return session.exec(
        select(Ingredient).where(func.lower(Ingredient.name) == name.strip().lower())
    ).first()


def _referencing_recipe_names(session: Session, ingredient_id: int) -> list[str]:
    return list(
        session.exec(
            select(Recipe.name)
            .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .where(RecipeIngredient.ingredient_id == ingredient_id)
            .distinct()
        )
    )


def _referenced_by_shopping_list_item(session: Session, ingredient_id: int) -> bool:
    return (
        session.exec(
            select(ShoppingListItem.id).where(
                ShoppingListItem.ingredient_id == ingredient_id
            )
        ).first()
        is not None
    )


@router.get("", response_model=list[IngredientOut])
def list_ingredients(
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[IngredientOut]:
    statement = select(Ingredient)
    if q:
        statement = statement.where(Ingredient.name.ilike(f"%{q}%"))
    ingredients = session.exec(statement.order_by(func.lower(Ingredient.name))).all()
    return [_to_out(session, i) for i in ingredients]


@router.post("", response_model=IngredientOut, status_code=status.HTTP_201_CREATED)
def create_ingredient(
    payload: IngredientIn, session: Session = Depends(get_session)
) -> IngredientOut:
    if _find_by_name(session, payload.name) is not None:
        raise AppError(409, "ingredient_exists", f"{payload.name} already exists")
    is_staple = (
        payload.is_staple
        if payload.is_staple is not None
        else payload.category.value == "seasoning"
    )
    ingredient = Ingredient(
        name=payload.name.strip(),
        category=payload.category,
        unit=payload.unit,
        is_staple=is_staple,
    )
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)
    return _to_out(session, ingredient)


@router.get("/{ingredient_id}", response_model=IngredientOut)
def get_ingredient(
    ingredient_id: int, session: Session = Depends(get_session)
) -> IngredientOut:
    return _to_out(session, _get_or_404(session, ingredient_id))


@router.patch("/{ingredient_id}", response_model=IngredientOut)
def update_ingredient(
    ingredient_id: int,
    payload: IngredientPatch,
    session: Session = Depends(get_session),
) -> IngredientOut:
    ingredient = _get_or_404(session, ingredient_id)
    changes = payload.model_dump(exclude_unset=True)

    if "unit" in changes and changes["unit"] != ingredient.unit:
        recipes = _referencing_recipe_names(session, ingredient_id)
        if recipes:
            raise AppError(
                409,
                "unit_locked",
                f"Cannot change the unit of {ingredient.name}: "
                f"used by {', '.join(recipes)}",
            )
    if "name" in changes:
        existing = _find_by_name(session, changes["name"])
        if existing is not None and existing.id != ingredient_id:
            raise AppError(
                409, "ingredient_exists", f"{changes['name']} already exists"
            )
        changes["name"] = changes["name"].strip()

    for key, value in changes.items():
        setattr(ingredient, key, value)
    session.add(ingredient)
    session.commit()
    session.refresh(ingredient)
    return _to_out(session, ingredient)


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingredient(
    ingredient_id: int, session: Session = Depends(get_session)
) -> Response:
    ingredient = _get_or_404(session, ingredient_id)
    recipes = _referencing_recipe_names(session, ingredient_id)
    if recipes:
        raise AppError(
            409,
            "ingredient_in_use",
            f"Can't delete {ingredient.name}: used by {', '.join(recipes)}",
        )
    if _referenced_by_shopping_list_item(session, ingredient_id):
        raise AppError(
            409,
            "ingredient_in_use",
            f"Can't delete {ingredient.name}: it's on a shopping list",
        )
    session.delete(ingredient)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
