from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import (
    CATEGORY_ORDER,
    DEFAULT_UNIT_FOR_CATEGORY,
    CanonicalUnit,
    Category,
    Ingredient,
    ItemSection,
    ItemSource,
    MealKind,
    MealPlan,
    MealSlot,
    PlanStatus,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
    Setting,
    ShoppingList,
    ShoppingListItem,
)


def test_category_defaults_cover_every_category():
    for category in Category:
        assert category in DEFAULT_UNIT_FOR_CATEGORY


def test_category_defaults_match_the_spec():
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.PRODUCE] is CanonicalUnit.COUNT
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.MEAT_SEAFOOD] is CanonicalUnit.G
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.DRY_GOODS] is CanonicalUnit.G
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.BAKERY] is CanonicalUnit.COUNT
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.DAIRY] is CanonicalUnit.ML
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.FROZEN] is CanonicalUnit.G
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.SEASONING] is CanonicalUnit.ML
    assert DEFAULT_UNIT_FOR_CATEGORY[Category.OTHER] is CanonicalUnit.COUNT


def test_category_order_is_store_walk_order():
    assert [c.value for c in CATEGORY_ORDER] == [
        "produce",
        "bakery",
        "meat_seafood",
        "dairy",
        "frozen",
        "dry_goods",
        "seasoning",
        "other",
    ]


def test_ingredient_name_is_unique(session):
    session.add(Ingredient(name="Onion", category=Category.PRODUCE, unit=CanonicalUnit.COUNT))
    session.commit()
    session.add(Ingredient(name="Onion", category=Category.PRODUCE, unit=CanonicalUnit.COUNT))
    with pytest.raises(IntegrityError):
        session.commit()


def test_recipe_round_trips_with_its_lines(session):
    onion = Ingredient(name="Onion", category=Category.PRODUCE, unit=CanonicalUnit.COUNT)
    session.add(onion)
    session.commit()

    recipe = Recipe(name="Chili", serves=4, instructions="Simmer.")
    session.add(recipe)
    session.commit()
    session.add(
        RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=onion.id,
            quantity=2.0,
            display_unit="count",
            prep_note="diced",
            position=0,
        )
    )
    session.commit()

    loaded = session.exec(select(Recipe).where(Recipe.name == "Chili")).one()
    assert loaded.serves == 4
    assert len(loaded.lines) == 1
    assert loaded.lines[0].prep_note == "diced"


def test_multiple_meals_per_slot(session):
    chili = Recipe(name="Chili", serves=4)
    soup = Recipe(name="Soup", serves=2)
    plan = MealPlan(week_start=date(2026, 8, 17))
    session.add(chili)
    session.add(soup)
    session.add(plan)
    session.commit()

    meal1 = PlannedMeal(
        plan_id=plan.id,
        day=0,
        slot=MealSlot.DINNER,
        recipe_id=chili.id,
        kind=MealKind.COOK,
        servings_to_make=4,
        servings_eaten=2,
    )
    meal2 = PlannedMeal(
        plan_id=plan.id,
        day=0,
        slot=MealSlot.DINNER,
        recipe_id=soup.id,
        kind=MealKind.COOK,
        servings_to_make=2,
        servings_eaten=2,
    )
    session.add(meal1)
    session.add(meal2)
    session.commit()

    meals = session.exec(
        select(PlannedMeal)
        .where(PlannedMeal.plan_id == plan.id)
        .where(PlannedMeal.day == 0)
        .where(PlannedMeal.slot == MealSlot.DINNER)
    ).all()
    assert len(meals) == 2
    assert {m.recipe_id for m in meals} == {chili.id, soup.id}


def test_week_start_is_unique(session):
    session.add(MealPlan(week_start=date(2026, 8, 17)))
    session.commit()
    session.add(MealPlan(week_start=date(2026, 8, 17)))
    with pytest.raises(IntegrityError):
        session.commit()


def test_shopping_list_item_stores_contributions_as_json(session):
    plan = MealPlan(week_start=date(2026, 8, 17))
    ingredient = Ingredient(name="Onion", category=Category.PRODUCE, unit=CanonicalUnit.COUNT)
    session.add(plan)
    session.add(ingredient)
    session.commit()

    shopping_list = ShoppingList(plan_id=plan.id)
    session.add(shopping_list)
    session.commit()

    item = ShoppingListItem(
        list_id=shopping_list.id,
        ingredient_id=ingredient.id,
        quantity=3.0,
        display_quantity=3.0,
        display_unit="count",
        source=ItemSource.RECIPE,
        section=ItemSection.BUY,
        contributions=[{"recipe_id": 1, "recipe_name": "Chili", "quantity": 2.0}],
    )
    session.add(item)
    session.commit()
    session.refresh(item)

    assert item.contributions[0]["recipe_name"] == "Chili"
    assert item.checked is False


def test_setting_defaults_household_size(session):
    setting = Setting()
    session.add(setting)
    session.commit()
    assert setting.household_size == 2


def test_plan_status_defaults_to_planning(session):
    plan = MealPlan(week_start=date(2026, 8, 17))
    session.add(plan)
    session.commit()
    assert plan.status is PlanStatus.PLANNING
