"""Repeat-buy detection over recently finalized lists.

Only manual items count: recipe-derived items already come back automatically
when you plan the recipe again, so suggesting them would be noise.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import Ingredient, ItemSource, ShoppingList, ShoppingListItem
from app.schemas import SuggestionOut

HISTORY_WINDOW = 4
APPEARANCE_THRESHOLD = 3


def item_key(ingredient_id: int | None, custom_name: str | None) -> str:
    """A stable identity for an item across weeks."""
    if ingredient_id is not None:
        return f"i:{ingredient_id}"
    return f"n:{(custom_name or '').strip().lower()}"


def suggest(session: Session, list_id: int) -> list[SuggestionOut]:
    current = session.get(ShoppingList, list_id)
    if current is None:
        return []

    already_present = {
        item_key(item.ingredient_id, item.custom_name) for item in current.items
    }

    recent = session.exec(
        select(ShoppingList)
        .where(ShoppingList.finalized_at.is_not(None))
        .where(ShoppingList.id != list_id)
        .order_by(ShoppingList.finalized_at.desc())
        .limit(HISTORY_WINDOW)
    ).all()

    counts: dict[str, int] = {}
    labels: dict[str, tuple[int | None, str]] = {}
    for shopping_list in recent:
        # Count each key once per week, not once per row.
        keys_this_week: dict[str, tuple[int | None, str]] = {}
        for item in shopping_list.items:
            if item.source is not ItemSource.MANUAL:
                continue
            key = item_key(item.ingredient_id, item.custom_name)
            if item.ingredient_id is not None:
                ingredient = session.get(Ingredient, item.ingredient_id)
                if ingredient is None:
                    # Defensive: FK constraints should make this unreachable,
                    # but never dereference a missing ingredient.
                    continue
                keys_this_week[key] = (item.ingredient_id, ingredient.name)
            else:
                keys_this_week[key] = (None, (item.custom_name or "").strip())
        for key, label in keys_this_week.items():
            counts[key] = counts.get(key, 0) + 1
            labels.setdefault(key, label)

    suggestions = [
        SuggestionOut(
            ingredient_id=labels[key][0], name=labels[key][1], times_bought=count
        )
        for key, count in counts.items()
        if count >= APPEARANCE_THRESHOLD and key not in already_present
    ]
    return sorted(suggestions, key=lambda s: (-s.times_bought, s.name.lower()))
