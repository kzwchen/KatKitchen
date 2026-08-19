"""SQLModel tables for KatKitchen.

Design note: an ingredient's `unit` is fixed at creation. Every recipe line
referencing that ingredient stores its quantity in that unit, which makes
aggregation across recipes plain addition and makes unit conflicts
unrepresentable.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Category(str, Enum):
    PRODUCE = "produce"
    BAKERY = "bakery"
    MEAT_SEAFOOD = "meat_seafood"
    DAIRY = "dairy"
    FROZEN = "frozen"
    DRY_GOODS = "dry_goods"
    SEASONING = "seasoning"
    OTHER = "other"


class CanonicalUnit(str, Enum):
    COUNT = "count"
    G = "g"
    ML = "ml"


class PlanStatus(str, Enum):
    PLANNING = "planning"
    SHOPPING = "shopping"
    DONE = "done"


class MealSlot(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class MealKind(str, Enum):
    COOK = "cook"
    LEFTOVERS = "leftovers"


class ItemSource(str, Enum):
    RECIPE = "recipe"
    MANUAL = "manual"
    SUGGESTED = "suggested"


class ItemSection(str, Enum):
    BUY = "buy"
    STAPLE_CHECK = "staple_check"


#: Store-walk order used to group the shopping list.
CATEGORY_ORDER: list[Category] = [
    Category.PRODUCE,
    Category.BAKERY,
    Category.MEAT_SEAFOOD,
    Category.DAIRY,
    Category.FROZEN,
    Category.DRY_GOODS,
    Category.SEASONING,
    Category.OTHER,
]

#: Suggested canonical unit when creating an ingredient. The user may override.
DEFAULT_UNIT_FOR_CATEGORY: dict[Category, CanonicalUnit] = {
    Category.PRODUCE: CanonicalUnit.COUNT,
    Category.BAKERY: CanonicalUnit.COUNT,
    Category.MEAT_SEAFOOD: CanonicalUnit.G,
    Category.DAIRY: CanonicalUnit.ML,
    Category.FROZEN: CanonicalUnit.G,
    Category.DRY_GOODS: CanonicalUnit.G,
    Category.SEASONING: CanonicalUnit.ML,
    Category.OTHER: CanonicalUnit.COUNT,
}


class Ingredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    category: Category
    unit: CanonicalUnit
    is_staple: bool = False

    lines: list["RecipeIngredient"] = Relationship(back_populates="ingredient")


class Recipe(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    serves: int = Field(default=2, ge=1)
    instructions: str = ""
    source_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    lines: list["RecipeIngredient"] = Relationship(
        back_populates="recipe",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "RecipeIngredient.position",
        },
    )


class RecipeIngredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    quantity: float
    display_unit: str
    prep_note: Optional[str] = None
    position: int = 0

    recipe: Optional[Recipe] = Relationship(back_populates="lines")
    ingredient: Optional[Ingredient] = Relationship(back_populates="lines")


class MealPlan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_start: date = Field(unique=True, index=True)
    status: PlanStatus = PlanStatus.PLANNING
    created_at: datetime = Field(default_factory=_now)

    meals: list["PlannedMeal"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    # A plan's shopping list is a derived, strictly 1:1 child (ShoppingList.plan_id
    # is unique) with no independent lifecycle of its own -- it only exists because
    # the plan does. Without this cascade, deleting a plan that already has a
    # generated list raised a raw IntegrityError (ShoppingList.plan_id is a real
    # FK), surfaced to callers as an unhandled 500.
    shopping_list: Optional["ShoppingList"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "uselist": False},
    )


class PlannedMeal(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("plan_id", "day", "slot", name="uq_plan_slot"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="mealplan.id", index=True)
    day: int = Field(ge=0, le=6)
    slot: MealSlot
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    kind: MealKind = MealKind.COOK
    servings_to_make: Optional[int] = None
    servings_eaten: int = 2
    source_meal_id: Optional[int] = Field(default=None, foreign_key="plannedmeal.id")

    plan: Optional[MealPlan] = Relationship(back_populates="meals")
    # source_meal_id is self-referencing: a leftovers slot points at the cook
    # meal it eats from. Declaring it as a relationship is what lets
    # SQLAlchemy's unit of work topologically sort deletes within this one
    # table, so the dependent (leftovers) row goes before the cook row it
    # references. Without it, deleting a plan whose week had a leftovers slot
    # emitted the deletes in arbitrary order and, with PRAGMA foreign_keys=ON,
    # raised "FOREIGN KEY constraint failed". `remote_side` is required on the
    # many-to-one side of a self-reference: it names the column that is the
    # "one" end (the primary key), which is the only way SQLAlchemy can tell
    # the two directions apart.
    source_meal: Optional["PlannedMeal"] = Relationship(
        back_populates="leftovers",
        sa_relationship_kwargs={"remote_side": "PlannedMeal.id"},
    )
    # Cascade, not just ordering: a leftovers slot cannot outlive the cook it
    # eats from. Deleting a cook meal on its own is still refused by
    # `delete_meal` (409 meal_has_leftovers), so in practice this fires only
    # when the whole plan goes.
    #
    # "all" and deliberately NOT "delete-orphan", unlike the collections
    # above: delete-orphan would read "a leftovers row that stops pointing at
    # a source is meaningless, delete it", but `update_meal` creates exactly
    # that row on purpose when a leftovers slot is converted back into a cook
    # (it nulls source_meal_id). "all" cascades the delete without claiming
    # the de-associated state is impossible.
    leftovers: list["PlannedMeal"] = Relationship(
        back_populates="source_meal",
        sa_relationship_kwargs={"cascade": "all"},
    )


class ShoppingList(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="mealplan.id", unique=True, index=True)
    generated_at: datetime = Field(default_factory=_now)
    finalized_at: Optional[datetime] = None

    items: list["ShoppingListItem"] = Relationship(
        back_populates="shopping_list",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    plan: Optional[MealPlan] = Relationship(back_populates="shopping_list")


class ShoppingListItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    list_id: int = Field(foreign_key="shoppinglist.id", index=True)
    ingredient_id: Optional[int] = Field(default=None, foreign_key="ingredient.id")
    custom_name: Optional[str] = None
    quantity: Optional[float] = None
    display_quantity: Optional[float] = None
    display_unit: Optional[str] = None
    source: ItemSource = ItemSource.RECIPE
    section: ItemSection = ItemSection.BUY
    checked: bool = False
    note: Optional[str] = None
    contributions: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )

    shopping_list: Optional[ShoppingList] = Relationship(back_populates="items")


class Setting(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    household_size: int = Field(default=2, ge=1)
