"""Pure construction of a shopping-list draft from a week's cook meals.

No database access and no I/O: everything the builder needs arrives as plain
dataclasses, which is what makes the rounding and aggregation rules cheap to
test exhaustively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.models import CATEGORY_ORDER, Category
from app.services.units import format_display, round_up


@dataclass(frozen=True)
class IngredientRef:
    id: int
    name: str
    category: Category
    unit: str
    is_staple: bool


@dataclass(frozen=True)
class RecipeLine:
    ingredient_id: int
    quantity: float


@dataclass(frozen=True)
class RecipeRef:
    id: int
    name: str
    serves: int
    lines: tuple[RecipeLine, ...] = ()


@dataclass(frozen=True)
class CookMeal:
    """A meal that is actually cooked. Leftover meals are never passed here."""

    recipe_id: int
    servings_to_make: int


@dataclass(frozen=True)
class Contribution:
    recipe_id: int
    recipe_name: str
    quantity: float


@dataclass(frozen=True)
class DraftItem:
    ingredient_id: int
    quantity: float | None
    display_quantity: float | None
    display_unit: str | None
    section: str
    contributions: tuple[Contribution, ...] = ()


_CATEGORY_RANK = {category: rank for rank, category in enumerate(CATEGORY_ORDER)}


def build_draft(
    meals: Sequence[CookMeal],
    recipes: Mapping[int, RecipeRef],
    ingredients: Mapping[int, IngredientRef],
) -> list[DraftItem]:
    """Aggregate a week of cook meals into an ordered list of draft items."""
    totals: dict[int, float] = {}
    contributions: dict[int, list[Contribution]] = {}

    for meal in meals:
        recipe = recipes[meal.recipe_id]
        scale = meal.servings_to_make / recipe.serves
        for line in recipe.lines:
            scaled = line.quantity * scale
            totals[line.ingredient_id] = totals.get(line.ingredient_id, 0.0) + scaled
            contributions.setdefault(line.ingredient_id, []).append(
                Contribution(recipe.id, recipe.name, scaled)
            )

    items: list[DraftItem] = []
    for ingredient_id, total in totals.items():
        ingredient = ingredients[ingredient_id]
        if ingredient.is_staple:
            items.append(
                DraftItem(
                    ingredient_id=ingredient_id,
                    quantity=None,
                    display_quantity=None,
                    display_unit=None,
                    section="staple_check",
                    contributions=tuple(contributions[ingredient_id]),
                )
            )
            continue

        # Rounding happens once, after summing every recipe's contribution.
        rounded = round_up(total, ingredient.unit)
        display_quantity, display_unit = format_display(rounded, ingredient.unit)
        items.append(
            DraftItem(
                ingredient_id=ingredient_id,
                quantity=rounded,
                display_quantity=display_quantity,
                display_unit=display_unit,
                section="buy",
                contributions=tuple(contributions[ingredient_id]),
            )
        )

    def sort_key(item: DraftItem) -> tuple[int, int, str]:
        ingredient = ingredients[item.ingredient_id]
        return (
            1 if item.section == "staple_check" else 0,
            _CATEGORY_RANK[ingredient.category],
            ingredient.name.lower(),
        )

    items.sort(key=sort_key)
    return items
