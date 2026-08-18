"""Persistence and regeneration for shopping lists.

`list_builder` stays pure; everything that touches the session lives here. The
merge rules exist so that editing the plan after you have started ticking boxes
never throws away work you did by hand.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import (
    Ingredient,
    ItemSection,
    ItemSource,
    MealKind,
    MealPlan,
    PlannedMeal,
    Recipe,
    ShoppingList,
    ShoppingListItem,
)
from app.services.list_builder import (
    CookMeal,
    IngredientRef,
    RecipeLine,
    RecipeRef,
    build_draft,
)

_SECTION = {"buy": ItemSection.BUY, "staple_check": ItemSection.STAPLE_CHECK}


def _cook_meals(session: Session, plan_id: int) -> list[CookMeal]:
    meals = session.exec(
        select(PlannedMeal)
        .where(PlannedMeal.plan_id == plan_id)
        .where(PlannedMeal.kind == MealKind.COOK)
    ).all()
    return [CookMeal(m.recipe_id, m.servings_to_make or 0) for m in meals]


def _recipe_refs(session: Session, meals: list[CookMeal]) -> dict[int, RecipeRef]:
    refs: dict[int, RecipeRef] = {}
    for meal in meals:
        if meal.recipe_id in refs:
            continue
        recipe = session.get(Recipe, meal.recipe_id)
        refs[recipe.id] = RecipeRef(
            id=recipe.id,
            name=recipe.name,
            serves=recipe.serves,
            lines=tuple(
                RecipeLine(line.ingredient_id, line.quantity) for line in recipe.lines
            ),
        )
    return refs


def _ingredient_refs(session: Session) -> dict[int, IngredientRef]:
    return {
        i.id: IngredientRef(i.id, i.name, i.category, i.unit.value, i.is_staple)
        for i in session.exec(select(Ingredient)).all()
    }


def generate(session: Session, plan_id: int) -> ShoppingList:
    """Create or regenerate the list for a plan, preserving hand-entered work."""
    plan = session.get(MealPlan, plan_id)
    shopping_list = session.exec(
        select(ShoppingList).where(ShoppingList.plan_id == plan_id)
    ).first()
    if shopping_list is None:
        shopping_list = ShoppingList(plan_id=plan_id)
        session.add(shopping_list)
        # flush (not commit) so this is part of the same transaction as the
        # rest of generate(): a failure below leaves nothing persisted.
        session.flush()

    meals = _cook_meals(session, plan_id)
    draft = build_draft(meals, _recipe_refs(session, meals), _ingredient_refs(session))

    existing = {
        item.ingredient_id: item
        for item in shopping_list.items
        if item.source is ItemSource.RECIPE and item.ingredient_id is not None
    }
    seen: set[int] = set()

    for entry in draft:
        seen.add(entry.ingredient_id)
        item = existing.get(entry.ingredient_id)
        if item is None:
            item = ShoppingListItem(
                list_id=shopping_list.id,
                ingredient_id=entry.ingredient_id,
                source=ItemSource.RECIPE,
            )
        # checked and note are deliberately left as they are.
        item.quantity = entry.quantity
        item.display_quantity = entry.display_quantity
        item.display_unit = entry.display_unit
        item.section = _SECTION[entry.section]
        item.contributions = [
            {
                "recipe_id": c.recipe_id,
                "recipe_name": c.recipe_name,
                "quantity": round(c.quantity, 4),
            }
            for c in entry.contributions
        ]
        session.add(item)

    for ingredient_id, item in existing.items():
        if ingredient_id not in seen:
            session.delete(item)

    shopping_list.generated_at = datetime.now(timezone.utc)
    session.add(shopping_list)
    session.commit()
    session.refresh(shopping_list)
    return shopping_list
