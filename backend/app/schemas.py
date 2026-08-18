"""Request and response models, kept separate from the tables so the wire
format can differ from storage (for example `usage_count`, which is derived)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.models import CanonicalUnit, Category


class IngredientIn(BaseModel):
    name: str = Field(min_length=1)
    category: Category
    unit: CanonicalUnit
    is_staple: Optional[bool] = None


class IngredientPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    category: Optional[Category] = None
    unit: Optional[CanonicalUnit] = None
    is_staple: Optional[bool] = None


class IngredientOut(BaseModel):
    id: int
    name: str
    category: Category
    unit: CanonicalUnit
    is_staple: bool
    usage_count: int


class SettingsOut(BaseModel):
    household_size: int


class SettingsPatch(BaseModel):
    household_size: int = Field(ge=1)


class RecipeLineIn(BaseModel):
    ingredient_id: int
    quantity: float = Field(gt=0)
    display_unit: str
    prep_note: Optional[str] = None


class RecipeLineOut(BaseModel):
    id: int
    ingredient_id: int
    ingredient_name: str
    ingredient_unit: CanonicalUnit
    category: Category
    quantity: float
    display_quantity: float
    display_unit: str
    prep_note: Optional[str] = None
    position: int


class RecipeIn(BaseModel):
    name: str = Field(min_length=1)
    serves: int = Field(ge=1)
    instructions: str = ""
    source_url: Optional[str] = None
    notes: Optional[str] = None
    lines: list[RecipeLineIn] = Field(default_factory=list)


class RecipePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    serves: Optional[int] = Field(default=None, ge=1)
    instructions: Optional[str] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None
    lines: Optional[list[RecipeLineIn]] = None


class RecipeOut(BaseModel):
    id: int
    name: str
    serves: int
    instructions: str
    source_url: Optional[str] = None
    notes: Optional[str] = None
    lines: list[RecipeLineOut]


class RecipeSummary(BaseModel):
    id: int
    name: str
    serves: int
    line_count: int


from datetime import date

from app.models import MealKind, MealSlot, PlanStatus


class PlanIn(BaseModel):
    week_start: date


class PlanSummary(BaseModel):
    id: int
    week_start: date
    status: PlanStatus
    meal_count: int
    has_list: bool


class MealIn(BaseModel):
    day: int = Field(ge=0, le=6)
    slot: MealSlot
    recipe_id: int
    kind: MealKind = MealKind.COOK
    servings_to_make: Optional[int] = Field(default=None, ge=1)
    servings_eaten: Optional[int] = Field(default=None, ge=1)
    source_meal_id: Optional[int] = None


class MealPatch(BaseModel):
    recipe_id: Optional[int] = None
    kind: Optional[MealKind] = None
    servings_to_make: Optional[int] = Field(default=None, ge=1)
    servings_eaten: Optional[int] = Field(default=None, ge=1)
    source_meal_id: Optional[int] = None


class MealOut(BaseModel):
    id: int
    day: int
    slot: MealSlot
    recipe_id: int
    recipe_name: str
    recipe_serves: int
    kind: MealKind
    servings_to_make: Optional[int]
    servings_eaten: int
    source_meal_id: Optional[int]


class SlotWarning(BaseModel):
    meal_id: int
    message: str


class PlanOut(BaseModel):
    id: int
    week_start: date
    status: PlanStatus
    meals: list[MealOut]
    warnings: list[SlotWarning]


from datetime import datetime
from typing import Any

from app.models import ItemSection, ItemSource


class ListItemIn(BaseModel):
    custom_name: Optional[str] = None
    ingredient_id: Optional[int] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    display_unit: Optional[str] = None
    note: Optional[str] = None


class ListItemPatch(BaseModel):
    checked: Optional[bool] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    display_unit: Optional[str] = None
    note: Optional[str] = None
    custom_name: Optional[str] = None


class ListItemOut(BaseModel):
    id: int
    ingredient_id: Optional[int]
    name: str
    category: Optional[Category]
    quantity: Optional[float]
    display_quantity: Optional[float]
    display_unit: Optional[str]
    source: ItemSource
    section: ItemSection
    checked: bool
    note: Optional[str]
    contributions: list[dict[str, Any]]


class ListOut(BaseModel):
    id: int
    plan_id: int
    week_start: date
    generated_at: datetime
    finalized_at: Optional[datetime]
    items: list[ListItemOut]


class ListSummary(BaseModel):
    id: int
    plan_id: int
    week_start: date
    finalized_at: Optional[datetime]
    item_count: int
    checked_count: int
