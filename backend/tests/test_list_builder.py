import pytest

from app.models import Category
from app.services.list_builder import (
    CookMeal,
    IngredientRef,
    RecipeLine,
    RecipeRef,
    build_draft,
)

ONION = IngredientRef(1, "Onion", Category.PRODUCE, "count", False)
CHICKEN = IngredientRef(2, "Chicken thigh", Category.MEAT_SEAFOOD, "g", False)
CUMIN = IngredientRef(3, "Cumin", Category.SEASONING, "ml", True)
PASTA = IngredientRef(4, "Pasta", Category.DRY_GOODS, "g", False)
APPLE = IngredientRef(5, "Apple", Category.PRODUCE, "count", False)

INGREDIENTS = {i.id: i for i in (ONION, CHICKEN, CUMIN, PASTA, APPLE)}


def recipe(rid, name, serves, lines):
    return RecipeRef(rid, name, serves, tuple(RecipeLine(*line) for line in lines))


CHILI = recipe(10, "Chili", 4, [(1, 2.0), (2, 500.0), (3, 5.0)])
PASTA_BAKE = recipe(11, "Pasta bake", 2, [(1, 1.0), (4, 200.0)])
RECIPES = {r.id: r for r in (CHILI, PASTA_BAKE)}


def by_ingredient(items):
    return {item.ingredient_id: item for item in items}


def test_single_recipe_at_base_servings_uses_recipe_quantities():
    items = by_ingredient(build_draft([CookMeal(10, 4)], RECIPES, INGREDIENTS))
    assert items[1].quantity == 2.0
    assert items[2].quantity == 500.0


def test_quantities_scale_with_servings_to_make():
    items = by_ingredient(build_draft([CookMeal(10, 8)], RECIPES, INGREDIENTS))
    assert items[1].quantity == 4.0
    assert items[2].quantity == 1000.0


def test_fractional_scaling_rounds_up_counts_to_whole():
    # 4 servings of chili scaled to 5 => 2 onions * 1.25 = 2.5 => 3
    items = by_ingredient(build_draft([CookMeal(10, 5)], RECIPES, INGREDIENTS))
    assert items[1].quantity == 3.0


def test_mass_rounds_up_to_the_next_ten_grams():
    # 500 g * 1.25 = 625 g => 630 g
    items = by_ingredient(build_draft([CookMeal(10, 5)], RECIPES, INGREDIENTS))
    assert items[2].quantity == 630.0


def test_quantities_sum_across_recipes():
    items = by_ingredient(
        build_draft([CookMeal(10, 4), CookMeal(11, 2)], RECIPES, INGREDIENTS)
    )
    assert items[1].quantity == 3.0  # 2 from chili + 1 from pasta bake


def test_rounding_is_applied_once_after_summing_not_per_recipe():
    # Two cook meals of a recipe that serves 5, each making 2 servings, so
    # 1 onion scales to 0.4 twice. Summed that is 0.8, which rounds up to
    # 1 onion, whereas rounding per recipe would give 1 + 1 = 2.
    small = recipe(12, "Small bake", 5, [(1, 1.0)])
    recipes = {**RECIPES, 12: small}
    items = by_ingredient(
        build_draft([CookMeal(12, 2), CookMeal(12, 2)], recipes, ingredients=INGREDIENTS)
    )
    assert items[1].quantity == 1.0


def test_contributions_record_each_recipe_and_its_unrounded_amount():
    items = by_ingredient(
        build_draft([CookMeal(10, 4), CookMeal(11, 2)], RECIPES, INGREDIENTS)
    )
    contributions = {c.recipe_name: c.quantity for c in items[1].contributions}
    assert contributions == {"Chili": 2.0, "Pasta bake": 1.0}


def test_staples_go_to_the_check_section_without_a_quantity():
    items = by_ingredient(build_draft([CookMeal(10, 4)], RECIPES, INGREDIENTS))
    cumin = items[3]
    assert cumin.section == "staple_check"
    assert cumin.quantity is None
    assert cumin.display_quantity is None
    assert [c.recipe_name for c in cumin.contributions] == ["Chili"]


def test_non_staples_go_to_the_buy_section():
    items = by_ingredient(build_draft([CookMeal(10, 4)], RECIPES, INGREDIENTS))
    assert items[1].section == "buy"


def test_display_unit_upgrades_to_kilograms_past_a_thousand_grams():
    items = by_ingredient(build_draft([CookMeal(10, 12)], RECIPES, INGREDIENTS))
    chicken = items[2]
    assert chicken.quantity == 1500.0
    assert (chicken.display_quantity, chicken.display_unit) == (1.5, "kg")


def test_buy_items_are_ordered_by_store_walk_then_name():
    items = build_draft([CookMeal(10, 4), CookMeal(11, 2)], RECIPES, INGREDIENTS)
    buy = [INGREDIENTS[i.ingredient_id].name for i in items if i.section == "buy"]
    assert buy == ["Onion", "Chicken thigh", "Pasta"]


def test_same_category_items_are_alphabetical():
    fruit = recipe(13, "Fruit salad", 1, [(5, 1.0), (1, 1.0)])
    items = build_draft([CookMeal(13, 1)], {13: fruit}, INGREDIENTS)
    names = [INGREDIENTS[i.ingredient_id].name for i in items]
    assert names == ["Apple", "Onion"]


def test_staple_items_are_ordered_after_all_buy_items():
    items = build_draft([CookMeal(10, 4)], RECIPES, INGREDIENTS)
    sections = [i.section for i in items]
    assert sections == sorted(sections, key=lambda s: s == "staple_check")
    assert sections[-1] == "staple_check"


def test_no_meals_produces_an_empty_draft():
    assert build_draft([], RECIPES, INGREDIENTS) == []


def test_unknown_recipe_id_raises():
    with pytest.raises(KeyError):
        build_draft([CookMeal(999, 2)], RECIPES, INGREDIENTS)
