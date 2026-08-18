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
