from datetime import date

import pytest
from sqlmodel import select

from app.models import (
    CanonicalUnit,
    Category,
    Ingredient,
    ItemSection,
    ItemSource,
    MealKind,
    MealPlan,
    MealSlot,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
)
from app.services.list_service import generate


@pytest.fixture
def world(session):
    """A plan with chili (Mon dinner, cook) and its leftovers (Tue lunch)."""
    onion = Ingredient(name="Onion", category=Category.PRODUCE, unit=CanonicalUnit.COUNT)
    cumin = Ingredient(
        name="Cumin", category=Category.SEASONING, unit=CanonicalUnit.ML, is_staple=True
    )
    session.add(onion)
    session.add(cumin)
    session.commit()

    chili = Recipe(name="Chili", serves=4, instructions="Simmer.")
    session.add(chili)
    session.commit()
    session.add(
        RecipeIngredient(
            recipe_id=chili.id, ingredient_id=onion.id, quantity=2.0,
            display_unit="count", position=0,
        )
    )
    session.add(
        RecipeIngredient(
            recipe_id=chili.id, ingredient_id=cumin.id, quantity=5.0,
            display_unit="tsp", position=1,
        )
    )

    plan = MealPlan(week_start=date(2026, 8, 17))
    session.add(plan)
    session.commit()

    cook = PlannedMeal(
        plan_id=plan.id, day=0, slot=MealSlot.DINNER, recipe_id=chili.id,
        kind=MealKind.COOK, servings_to_make=4, servings_eaten=2,
    )
    session.add(cook)
    session.commit()
    session.add(
        PlannedMeal(
            # servings_to_make is set here even though the plans router
            # always nulls it for leftovers (see app/routers/plans.py). That
            # is deliberate: it makes this row a live trap for the `kind`
            # filter in `_cook_meals`. If that filter is ever dropped, this
            # meal contributes a *nonzero* batch instead of silently no-op'ing
            # via `servings_to_make or 0`, so the test below actually notices.
            plan_id=plan.id, day=1, slot=MealSlot.LUNCH, recipe_id=chili.id,
            kind=MealKind.LEFTOVERS, servings_to_make=4, servings_eaten=2,
            source_meal_id=cook.id,
        )
    )
    session.commit()
    return {"plan": plan, "onion": onion, "cumin": cumin, "chili": chili, "cook": cook}


def items_by_ingredient(shopping_list):
    return {item.ingredient_id: item for item in shopping_list.items}


def test_generate_creates_a_list_from_cook_meals(session, world):
    shopping_list = generate(session, world["plan"].id)
    items = items_by_ingredient(shopping_list)
    assert items[world["onion"].id].quantity == 2.0
    assert items[world["onion"].id].section is ItemSection.BUY
    assert items[world["onion"].id].source is ItemSource.RECIPE


def test_leftover_meals_do_not_add_ingredients(session, world):
    # The plan has one cook (4 servings) and one leftovers slot. If leftovers
    # counted, the onion total would be 4 rather than 2.
    shopping_list = generate(session, world["plan"].id)
    assert items_by_ingredient(shopping_list)[world["onion"].id].quantity == 2.0


def test_staples_land_in_the_check_section(session, world):
    shopping_list = generate(session, world["plan"].id)
    cumin_item = items_by_ingredient(shopping_list)[world["cumin"].id]
    assert cumin_item.section is ItemSection.STAPLE_CHECK
    assert cumin_item.quantity is None
    assert cumin_item.contributions[0]["recipe_name"] == "Chili"


def test_regenerating_is_idempotent(session, world):
    first = generate(session, world["plan"].id)
    first_id = first.id
    count = len(first.items)
    second = generate(session, world["plan"].id)
    assert second.id == first_id
    assert len(second.items) == count


def test_regenerating_preserves_manual_items(session, world):
    shopping_list = generate(session, world["plan"].id)
    session.add(
        ShoppingListItem(
            list_id=shopping_list.id, custom_name="Paper towels",
            source=ItemSource.MANUAL, section=ItemSection.BUY, checked=True,
        )
    )
    session.commit()

    regenerated = generate(session, world["plan"].id)
    manual = [i for i in regenerated.items if i.source is ItemSource.MANUAL]
    assert len(manual) == 1
    assert manual[0].custom_name == "Paper towels"
    assert manual[0].checked is True


def test_regenerating_leaves_a_suggested_item_that_shares_a_recipe_ingredient(
    session, world
):
    """The merge must key its existing-item lookup on source, not just on
    ingredient_id.

    This is the live suggestion-chip path: accepting a repeat-buy suggestion
    creates an item that carries an `ingredient_id` and a non-RECIPE source.
    The suggested onion below is created *before* the first generate() so it
    is the only row holding that ingredient_id, which makes the outcome
    independent of the order `shopping_list.items` happens to load in. Drop
    the `source is ItemSource.RECIPE` filter in list_service.generate and
    regeneration hijacks this row -- overwriting the user's quantity with the
    recipe total and never creating a recipe row of its own.
    """
    shopping_list = ShoppingList(plan_id=world["plan"].id)
    session.add(shopping_list)
    session.commit()
    session.add(
        ShoppingListItem(
            list_id=shopping_list.id,
            ingredient_id=world["onion"].id,
            source=ItemSource.SUGGESTED,
            section=ItemSection.BUY,
            quantity=1.0,
            display_quantity=1.0,
            display_unit="count",
            checked=True,
            note="you buy these most weeks",
        )
    )
    session.commit()

    regenerated = generate(session, world["plan"].id)

    suggested = [i for i in regenerated.items if i.source is ItemSource.SUGGESTED]
    assert len(suggested) == 1
    assert suggested[0].ingredient_id == world["onion"].id
    assert suggested[0].quantity == 1.0
    assert suggested[0].checked is True
    assert suggested[0].note == "you buy these most weeks"

    recipe_onions = [
        i
        for i in regenerated.items
        if i.source is ItemSource.RECIPE and i.ingredient_id == world["onion"].id
    ]
    assert len(recipe_onions) == 1
    assert recipe_onions[0].quantity == 2.0


def test_regenerating_preserves_checked_state_across_a_quantity_change(session, world):
    shopping_list = generate(session, world["plan"].id)
    onion_item = items_by_ingredient(shopping_list)[world["onion"].id]
    onion_item.checked = True
    onion_item.note = "the big ones"
    session.add(onion_item)
    session.commit()

    world["cook"].servings_to_make = 8
    session.add(world["cook"])
    session.commit()

    regenerated = generate(session, world["plan"].id)
    updated = items_by_ingredient(regenerated)[world["onion"].id]
    assert updated.quantity == 4.0
    assert updated.checked is True
    assert updated.note == "the big ones"


def test_regenerating_drops_a_recipe_item_that_no_longer_applies(session, world):
    shopping_list = generate(session, world["plan"].id)
    onion_item = items_by_ingredient(shopping_list)[world["onion"].id]
    onion_item.checked = True
    session.add(onion_item)
    session.commit()

    # PlannedMeal.source_meal (self-referencing) is a declared relationship,
    # so the unit of work orders these deletes itself -- no need to hand-sort
    # leftovers before the cook meal they point at.
    for meal in session.exec(select(PlannedMeal)).all():
        session.delete(meal)
    session.commit()

    regenerated = generate(session, world["plan"].id)
    assert regenerated.items == []


def test_generate_is_atomic_when_a_later_step_fails(session, world, monkeypatch):
    # Simulate a failure that happens after the ShoppingList row would be
    # created but before generate() finishes. If the initial row creation
    # commits on its own (rather than merely flushing), that empty row is
    # left behind as an orphan even though the whole call raised.
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.list_service.build_draft", boom)

    with pytest.raises(RuntimeError):
        generate(session, world["plan"].id)

    session.rollback()
    assert session.exec(select(ShoppingList)).all() == []


def test_regenerating_keeps_a_manual_item_even_with_no_meals(session, world):
    shopping_list = generate(session, world["plan"].id)
    session.add(
        ShoppingListItem(
            list_id=shopping_list.id, custom_name="Coffee",
            source=ItemSource.MANUAL, section=ItemSection.BUY,
        )
    )
    session.commit()
    for meal in session.exec(select(PlannedMeal)).all():
        session.delete(meal)
    session.commit()

    regenerated = generate(session, world["plan"].id)
    assert [i.custom_name for i in regenerated.items] == ["Coffee"]
