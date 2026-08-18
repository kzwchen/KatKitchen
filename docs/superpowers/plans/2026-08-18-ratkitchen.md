# RatKitchen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local single-user web app that stores recipes with structured ingredient amounts, plans a week of meals day-by-day, and generates one accurate aisle-grouped printable shopping list.

**Architecture:** A FastAPI + SQLModel + SQLite backend where all interesting logic lives in three pure, heavily-tested services (unit conversion, shopping-list construction, repeat-buy suggestions) with thin routers over them. A React + TypeScript + Vite frontend talks to it over `/api` using TanStack Query, with no client-side global state. Correctness comes from the data model: each ingredient's unit is fixed at creation, so summing across recipes is plain addition and unit conflicts are unrepresentable.

**Tech Stack:** Python 3.11+, FastAPI, SQLModel, SQLite, pytest, uvicorn; Node 20+, React 18, TypeScript, Vite, TanStack Query, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-18-ratkitchen-design.md`

## Global Constraints

- Python 3.11 or later. Node 20 or later.
- Server binds `127.0.0.1` only. No authentication, no CORS to external origins.
- Database file: `data/ratkitchen.db`. It is gitignored; never commit it.
- All API routes are prefixed `/api`.
- Errors return JSON `{"detail": str, "code": str}`.
- Canonical storage units are exactly `count`, `g`, `ml`. Cross-family conversion is never performed.
- Quantities round **up**, never down.
- Store-walk category order is fixed: `produce`, `bakery`, `meat_seafood`, `dairy`, `frozen`, `dry_goods`, `seasoning`, `other`.
- TDD is mandatory: every task writes a failing test first, watches it fail, then implements.
- Commit at the end of every task.

## File Structure

```
backend/
  pyproject.toml
  app/
    main.py            FastAPI app, router registration, static/dev config
    db.py              engine, session dependency, create_all
    models.py          all SQLModel tables and enums
    schemas.py         request/response Pydantic models
    errors.py          AppError + exception handler producing {detail, code}
    routers/
      ingredients.py   ingredient CRUD + delete/unit-change protection
      recipes.py       recipe CRUD with nested ingredient lines
      plans.py         meal plan CRUD + planned meal slots
      lists.py         list generation, items, finalize, history
      settings.py      household_size
    services/
      units.py         unit families, exact conversion, round-up, display
      list_builder.py  pure build_draft(): meals+recipes -> draft items
      list_service.py  persistence + regeneration merge rules
      suggestions.py   repeat-buy detection over finalized lists
  tests/
    test_units.py  test_models.py  test_list_builder.py
    test_list_service.py  test_suggestions.py
    test_ingredients_api.py  test_recipes_api.py
    test_plans_api.py  test_lists_api.py
    conftest.py
frontend/
  package.json  vite.config.ts  tsconfig.json  vitest.config.ts
  src/
    main.tsx  App.tsx  print.css
    types/index.ts         TS mirrors of the API schemas
    api/client.ts          fetch wrapper + typed endpoint functions
    api/hooks.ts           TanStack Query hooks
    components/            Layout, Toast, QuantityInput, IngredientPicker, RecipePicker
    pages/Ingredients/  pages/Recipes/  pages/RecipeEditor/
    pages/Planner/  pages/ShoppingList/  pages/History/
data/                      gitignored database location
dev.ps1                    starts uvicorn + vite together
README.md
```

`services/list_service.py` is an addition to the spec's layout: the spec folded
persistence into `list_builder.py`, but keeping `list_builder.py` pure (no
session, no I/O) is what makes it cheaply testable, so the merge/persistence
half lives in its own module.

---

### Task 1: Backend scaffold and the units service

The unit service is the foundation every later task converts through, so the
project scaffold is folded in here rather than given its own task.

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`, `backend/app/services/__init__.py`
- Create: `backend/app/services/units.py`
- Create: `backend/tests/__init__.py`
- Test: `backend/tests/test_units.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class UnitFamily(str, Enum)` with `COUNT = "count"`, `MASS = "mass"`, `VOLUME = "volume"`
  - `CANONICAL: dict[UnitFamily, str]` mapping family to `"count"` / `"g"` / `"ml"`
  - `CONVERSIONS: dict[str, tuple[UnitFamily, float]]` mapping an entry unit to its family and factor-to-canonical
  - `class UnitError(ValueError)`
  - `family_of(unit: str) -> UnitFamily`
  - `to_canonical(quantity: float, entry_unit: str, canonical_unit: str) -> float`
  - `round_up(quantity: float, canonical_unit: str) -> float`
  - `format_display(quantity: float, canonical_unit: str) -> tuple[float, str]`

- [ ] **Step 1: Create the Python project scaffold**

Create `backend/pyproject.toml`:

```toml
[project]
name = "ratkitchen-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "sqlmodel>=0.0.16",
    "uvicorn[standard]>=0.29",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

Create empty `backend/app/__init__.py`, `backend/app/services/__init__.py`,
and `backend/tests/__init__.py`.

Then, from `backend/`:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_units.py`:

```python
import math
import pytest

from app.services.units import (
    UnitError,
    UnitFamily,
    family_of,
    format_display,
    round_up,
    to_canonical,
)


def test_family_of_recognises_each_family():
    assert family_of("count") is UnitFamily.COUNT
    assert family_of("kg") is UnitFamily.MASS
    assert family_of("tbsp") is UnitFamily.VOLUME


def test_family_of_rejects_unknown_unit():
    with pytest.raises(UnitError):
        family_of("furlong")


@pytest.mark.parametrize(
    "quantity,entry_unit,expected",
    [
        (1, "kg", 1000.0),
        (250, "g", 250.0),
        (1, "lb", 453.59237),
        (16, "oz", 453.592370),
    ],
)
def test_to_canonical_mass(quantity, entry_unit, expected):
    assert to_canonical(quantity, entry_unit, "g") == pytest.approx(expected)


@pytest.mark.parametrize(
    "quantity,entry_unit,expected",
    [
        (1, "l", 1000.0),
        (2, "tbsp", 30.0),
        (3, "tsp", 15.0),
        (0.5, "cup", 120.0),
    ],
)
def test_to_canonical_volume(quantity, entry_unit, expected):
    assert to_canonical(quantity, entry_unit, "ml") == pytest.approx(expected)


def test_to_canonical_count_is_identity():
    assert to_canonical(3, "count", "count") == 3.0


def test_to_canonical_rejects_cross_family():
    with pytest.raises(UnitError) as exc:
        to_canonical(1, "cup", "g")
    assert "cup" in str(exc.value)


def test_to_canonical_rejects_negative():
    with pytest.raises(UnitError):
        to_canonical(-1, "g", "g")


@pytest.mark.parametrize(
    "quantity,unit,expected",
    [
        (2.4, "count", 3.0),
        (2.0, "count", 2.0),
        (0.1, "count", 1.0),
        (141.0, "g", 150.0),
        (150.0, "g", 150.0),
        (150.0000000001, "g", 150.0),
        (0.0, "g", 0.0),
        (1.0, "ml", 10.0),
    ],
)
def test_round_up(quantity, unit, expected):
    assert round_up(quantity, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    "quantity,unit,expected",
    [
        (900.0, "g", (900.0, "g")),
        (1000.0, "g", (1.0, "kg")),
        (1200.0, "g", (1.2, "kg")),
        (999.0, "ml", (999.0, "ml")),
        (1500.0, "ml", (1.5, "l")),
        (3.0, "count", (3.0, "count")),
    ],
)
def test_format_display(quantity, unit, expected):
    assert format_display(quantity, unit) == expected
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_units.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.units'`.

- [ ] **Step 4: Implement the units service**

Create `backend/app/services/units.py`:

```python
"""Unit families, exact conversion, and display formatting.

Quantities are always stored in an ingredient's canonical unit. The user may
enter any unit in the same family; conversion is exact and needs no
per-ingredient data. Cross-family conversion is never attempted.
"""

from __future__ import annotations

import math
from enum import Enum


class UnitFamily(str, Enum):
    COUNT = "count"
    MASS = "mass"
    VOLUME = "volume"


class UnitError(ValueError):
    """Raised for an unknown unit, a cross-family conversion, or a bad quantity."""


CANONICAL: dict[UnitFamily, str] = {
    UnitFamily.COUNT: "count",
    UnitFamily.MASS: "g",
    UnitFamily.VOLUME: "ml",
}

# entry unit -> (family, factor converting one entry unit to one canonical unit)
CONVERSIONS: dict[str, tuple[UnitFamily, float]] = {
    "count": (UnitFamily.COUNT, 1.0),
    "g": (UnitFamily.MASS, 1.0),
    "kg": (UnitFamily.MASS, 1000.0),
    "oz": (UnitFamily.MASS, 28.349523125),
    "lb": (UnitFamily.MASS, 453.59237),
    "ml": (UnitFamily.VOLUME, 1.0),
    "l": (UnitFamily.VOLUME, 1000.0),
    "tsp": (UnitFamily.VOLUME, 5.0),
    "tbsp": (UnitFamily.VOLUME, 15.0),
    "cup": (UnitFamily.VOLUME, 240.0),
}

# Rounding granularity per canonical unit, applied once after summing.
_ROUND_STEP: dict[str, float] = {"count": 1.0, "g": 10.0, "ml": 10.0}

# Tolerance so float noise does not push a value onto the next step.
_EPSILON = 1e-9


def family_of(unit: str) -> UnitFamily:
    try:
        return CONVERSIONS[unit][0]
    except KeyError:
        raise UnitError(f"Unknown unit {unit!r}") from None


def to_canonical(quantity: float, entry_unit: str, canonical_unit: str) -> float:
    """Convert a user-entered quantity into an ingredient's canonical unit."""
    if quantity < 0:
        raise UnitError("Quantity must not be negative")
    entry_family = family_of(entry_unit)
    target_family = family_of(canonical_unit)
    if entry_family is not target_family:
        raise UnitError(
            f"Cannot convert {entry_unit!r} ({entry_family.value}) "
            f"to {canonical_unit!r} ({target_family.value})"
        )
    return float(quantity) * CONVERSIONS[entry_unit][1]


def round_up(quantity: float, canonical_unit: str) -> float:
    """Round a summed quantity up to the next purchasable step."""
    step = _ROUND_STEP[canonical_unit]
    if quantity <= 0:
        return 0.0
    return math.ceil(quantity / step - _EPSILON) * step


def format_display(quantity: float, canonical_unit: str) -> tuple[float, str]:
    """Pick the friendliest same-family unit for showing a canonical quantity."""
    if canonical_unit == "g" and quantity >= 1000:
        return (round(quantity / 1000, 3), "kg")
    if canonical_unit == "ml" and quantity >= 1000:
        return (round(quantity / 1000, 3), "l")
    return (quantity, canonical_unit)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_units.py -v`

Expected: PASS, 25 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app backend/tests
git commit -m "feat: add backend scaffold and unit conversion service"
```

---

### Task 2: Data model and database session

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/db.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `app.services.units.CANONICAL`, `UnitFamily` (for the category-to-unit default table).
- Produces:
  - Enums: `Category`, `CanonicalUnit`, `PlanStatus`, `MealSlot`, `MealKind`, `ItemSource`, `ItemSection`
  - Tables: `Ingredient`, `Recipe`, `RecipeIngredient`, `MealPlan`, `PlannedMeal`, `ShoppingList`, `ShoppingListItem`, `Setting`
  - `DEFAULT_UNIT_FOR_CATEGORY: dict[Category, CanonicalUnit]`
  - `CATEGORY_ORDER: list[Category]`
  - `app.db.engine`, `app.db.init_db() -> None`, `app.db.get_session()` (FastAPI dependency yielding a `Session`)
  - Test fixtures `session` (in-memory SQLite) and `client` (TestClient) in `conftest.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_models.py`:

```python
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


def test_one_meal_per_slot(session):
    recipe = Recipe(name="Chili", serves=4)
    plan = MealPlan(week_start="2026-08-17")
    session.add(recipe)
    session.add(plan)
    session.commit()

    for _ in range(2):
        session.add(
            PlannedMeal(
                plan_id=plan.id,
                day=0,
                slot=MealSlot.DINNER,
                recipe_id=recipe.id,
                kind=MealKind.COOK,
                servings_to_make=4,
                servings_eaten=2,
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()


def test_week_start_is_unique(session):
    session.add(MealPlan(week_start="2026-08-17"))
    session.commit()
    session.add(MealPlan(week_start="2026-08-17"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_shopping_list_item_stores_contributions_as_json(session):
    plan = MealPlan(week_start="2026-08-17")
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
    plan = MealPlan(week_start="2026-08-17")
    session.add(plan)
    session.commit()
    assert plan.status is PlanStatus.PLANNING
```

Create `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import for side effect: registers every table on SQLModel.metadata.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(engine):
    from app.db import get_session
    from app.main import app

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_models.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.models'`.

- [ ] **Step 3: Implement the models**

Create `backend/app/models.py`:

```python
"""SQLModel tables for RatKitchen.

Design note: an ingredient's `unit` is fixed at creation. Every recipe line
referencing that ingredient stores its quantity in that unit, which makes
aggregation across recipes plain addition and makes unit conflicts
unrepresentable.
"""

from __future__ import annotations

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


class ShoppingList(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="mealplan.id", unique=True, index=True)
    generated_at: datetime = Field(default_factory=_now)
    finalized_at: Optional[datetime] = None

    items: list["ShoppingListItem"] = Relationship(
        back_populates="shopping_list",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


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
```

- [ ] **Step 4: Implement the database module**

Create `backend/app/db.py`:

```python
"""Engine, schema creation, and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "ratkitchen.db"

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enforce_foreign_keys(dbapi_connection, _record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


def init_db() -> None:
    """Create the data directory, the schema, and the singleton settings row."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    import app.models as models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(models.Setting, 1) is None:
            session.add(models.Setting(id=1))
            session.commit()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_models.py -v`

Expected: PASS, 10 tests. (`test_models.py` uses only the `session` fixture, so
the `client` fixture's import of `app.main` is not exercised yet.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/tests
git commit -m "feat: add data model and database session"
```

---

### Task 3: The pure shopping-list builder

This is the correctness core of the whole app. It takes plain dataclasses in
and returns plain dataclasses out — no session, no I/O — so it can be tested
exhaustively and cheaply.

**Files:**
- Create: `backend/app/services/list_builder.py`
- Test: `backend/tests/test_list_builder.py`

**Interfaces:**
- Consumes: `app.services.units.round_up`, `format_display`; `app.models.CATEGORY_ORDER`, `Category`.
- Produces:
  - `@dataclass(frozen=True) IngredientRef(id: int, name: str, category: Category, unit: str, is_staple: bool)`
  - `@dataclass(frozen=True) RecipeLine(ingredient_id: int, quantity: float)`
  - `@dataclass(frozen=True) RecipeRef(id: int, name: str, serves: int, lines: tuple[RecipeLine, ...])`
  - `@dataclass(frozen=True) CookMeal(recipe_id: int, servings_to_make: int)`
  - `@dataclass(frozen=True) Contribution(recipe_id: int, recipe_name: str, quantity: float)`
  - `@dataclass(frozen=True) DraftItem(ingredient_id: int, quantity: float | None, display_quantity: float | None, display_unit: str | None, section: str, contributions: tuple[Contribution, ...])`
  - `build_draft(meals: Sequence[CookMeal], recipes: Mapping[int, RecipeRef], ingredients: Mapping[int, IngredientRef]) -> list[DraftItem]`

Callers pass only `cook` meals. Leftover meals are excluded by the caller
constructing the `CookMeal` sequence, and Task 7 has a test proving it.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_list_builder.py`:

```python
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
    # Two half-servings of pasta bake: 100 g + 100 g = 200 g exactly.
    # Rounding per recipe would give 100 + 100 = 200 too, so use a case that
    # differs: 0.6 servings each => 60 g + 60 g = 120 g. Per-recipe rounding
    # would give 60 -> 60 and 60 -> 60 = 120. Use counts instead, where the
    # difference is visible: 1 onion * 0.6 = 0.6 twice.
    # Summed:  0.6 + 0.6 = 1.2 -> 2 onions.
    # Per-recipe: ceil(0.6) + ceil(0.6) = 1 + 1 = 2. Same. So use 0.4:
    # Summed: 0.4 + 0.4 = 0.8 -> 1 onion. Per-recipe: 1 + 1 = 2.
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_list_builder.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.list_builder'`.

- [ ] **Step 3: Implement the builder**

Create `backend/app/services/list_builder.py`:

```python
"""Pure construction of a shopping-list draft from a week's cook meals.

No database access and no I/O: everything the builder needs arrives as plain
dataclasses, which is what makes the rounding and aggregation rules cheap to
test exhaustively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_list_builder.py -v`

Expected: PASS, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/list_builder.py backend/tests/test_list_builder.py
git commit -m "feat: add pure shopping list builder with round-up aggregation"
```

---

### Task 4: App wiring, error contract, ingredients and settings API

The FastAPI app object, the error contract, and the shared schema module are
folded in here because the ingredients router is the first thing that needs
them.

**Files:**
- Create: `backend/app/errors.py`, `backend/app/schemas.py`, `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`, `backend/app/routers/ingredients.py`, `backend/app/routers/settings.py`
- Test: `backend/tests/test_ingredients_api.py`

**Interfaces:**
- Consumes: `app.models` (all), `app.db.get_session`, `app.db.init_db`.
- Produces:
  - `class AppError(Exception)` with `__init__(self, status_code: int, code: str, detail: str)`
  - `app.main.app` — the FastAPI instance, with `app_error_handler` registered
  - `IngredientIn`, `IngredientPatch`, `IngredientOut`, `SettingsOut`, `SettingsPatch` in `schemas.py`
  - Routes: `GET/POST /api/ingredients`, `GET/PATCH/DELETE /api/ingredients/{id}`, `GET/PATCH /api/settings`
  - `IngredientOut` fields: `id`, `name`, `category`, `unit`, `is_staple`, `usage_count`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_ingredients_api.py`:

```python
import pytest

RECIPES_LAND_IN_TASK_5 = pytest.mark.xfail(
    reason="recipes router lands in Task 5", strict=True
)


def create_ingredient(client, **overrides):
    payload = {"name": "Onion", "category": "produce", "unit": "count", "is_staple": False}
    payload.update(overrides)
    return client.post("/api/ingredients", json=payload)


def add_recipe(client, ingredient_id, name="Chili", quantity=2, display_unit="count"):
    return client.post(
        "/api/recipes",
        json={
            "name": name,
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {
                    "ingredient_id": ingredient_id,
                    "quantity": quantity,
                    "display_unit": display_unit,
                }
            ],
        },
    )


def test_create_returns_the_ingredient(client):
    response = create_ingredient(client)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Onion"
    assert body["unit"] == "count"
    assert body["usage_count"] == 0


def test_create_rejects_a_duplicate_name_case_insensitively(client):
    create_ingredient(client)
    response = create_ingredient(client, name="onion")
    assert response.status_code == 409
    assert response.json()["code"] == "ingredient_exists"


def test_create_defaults_seasonings_to_staple(client):
    payload = {"name": "Cumin", "category": "seasoning", "unit": "ml"}
    response = client.post("/api/ingredients", json=payload)
    assert response.json()["is_staple"] is True


def test_create_rejects_a_unit_that_is_not_canonical(client):
    response = create_ingredient(client, name="Flour", category="dry_goods", unit="kg")
    assert response.status_code == 422


def test_list_supports_search(client):
    create_ingredient(client, name="Onion")
    create_ingredient(client, name="Chicken thigh", category="meat_seafood", unit="g")
    results = client.get("/api/ingredients", params={"q": "chick"}).json()
    assert [i["name"] for i in results] == ["Chicken thigh"]


def test_list_is_alphabetical(client):
    create_ingredient(client, name="Pasta", category="dry_goods", unit="g")
    create_ingredient(client, name="Apple")
    results = client.get("/api/ingredients").json()
    assert [i["name"] for i in results] == ["Apple", "Pasta"]


def test_patch_updates_name_and_staple_flag(client):
    ingredient_id = create_ingredient(client).json()["id"]
    response = client.patch(
        f"/api/ingredients/{ingredient_id}", json={"name": "Red onion", "is_staple": True}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Red onion"
    assert response.json()["is_staple"] is True


def test_delete_removes_an_unused_ingredient(client):
    ingredient_id = create_ingredient(client).json()["id"]
    assert client.delete(f"/api/ingredients/{ingredient_id}").status_code == 204
    assert client.get(f"/api/ingredients/{ingredient_id}").status_code == 404


def test_changing_unit_is_allowed_while_unused(client):
    ingredient_id = create_ingredient(
        client, name="Spinach", category="produce", unit="count"
    ).json()["id"]
    response = client.patch(f"/api/ingredients/{ingredient_id}", json={"unit": "g"})
    assert response.status_code == 200
    assert response.json()["unit"] == "g"


@RECIPES_LAND_IN_TASK_5
def test_delete_is_refused_when_a_recipe_uses_it(client):
    ingredient_id = create_ingredient(client).json()["id"]
    add_recipe(client, ingredient_id)
    response = client.delete(f"/api/ingredients/{ingredient_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "ingredient_in_use"
    assert "Chili" in response.json()["detail"]


@RECIPES_LAND_IN_TASK_5
def test_changing_unit_is_refused_when_a_recipe_uses_it(client):
    ingredient_id = create_ingredient(
        client, name="Flour", category="dry_goods", unit="g"
    ).json()["id"]
    add_recipe(client, ingredient_id, name="Bread", quantity=500, display_unit="g")
    response = client.patch(f"/api/ingredients/{ingredient_id}", json={"unit": "ml"})
    assert response.status_code == 409
    assert response.json()["code"] == "unit_locked"


@RECIPES_LAND_IN_TASK_5
def test_usage_count_reflects_recipes(client):
    ingredient_id = create_ingredient(client).json()["id"]
    add_recipe(client, ingredient_id)
    assert client.get(f"/api/ingredients/{ingredient_id}").json()["usage_count"] == 1


def test_settings_default_and_patch(client):
    assert client.get("/api/settings").json()["household_size"] == 2
    response = client.patch("/api/settings", json={"household_size": 4})
    assert response.json()["household_size"] == 4
    assert client.get("/api/settings").json()["household_size"] == 4
```

The three tests marked `RECIPES_LAND_IN_TASK_5` exercise behaviour this task
implements but cannot yet reach, because they need the recipes router. Task 5
removes the marker.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_ingredients_api.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Implement the error contract**

Create `backend/app/errors.py`:

```python
"""A single error shape for the whole API: {"detail": str, "code": str}."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )
```

- [ ] **Step 4: Implement the schemas used by this task**

Create `backend/app/schemas.py`. Later tasks append to this file; start with:

```python
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
```

- [ ] **Step 5: Implement the ingredients router**

Create an empty `backend/app/routers/__init__.py`, then
`backend/app/routers/ingredients.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import Ingredient, Recipe, RecipeIngredient
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
    session.delete(ingredient)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 6: Implement the settings router**

Create `backend/app/routers/settings.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.models import Setting
from app.schemas import SettingsOut, SettingsPatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


def get_or_create(session: Session) -> Setting:
    setting = session.get(Setting, 1)
    if setting is None:
        setting = Setting(id=1)
        session.add(setting)
        session.commit()
        session.refresh(setting)
    return setting


@router.get("", response_model=SettingsOut)
def read_settings(session: Session = Depends(get_session)) -> SettingsOut:
    return SettingsOut(household_size=get_or_create(session).household_size)


@router.patch("", response_model=SettingsOut)
def update_settings(
    payload: SettingsPatch, session: Session = Depends(get_session)
) -> SettingsOut:
    setting = get_or_create(session)
    setting.household_size = payload.household_size
    session.add(setting)
    session.commit()
    session.refresh(setting)
    return SettingsOut(household_size=setting.household_size)
```

- [ ] **Step 7: Implement the app**

Create `backend/app/main.py`. Later tasks add to the `include_router` block:

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.errors import AppError, app_error_handler
from app.routers import ingredients, settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="RatKitchen", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)

app.include_router(ingredients.router)
app.include_router(settings.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -v`

Expected: PASS, with the three recipe-dependent tests reported as `xfail`.

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/test_ingredients_api.py
git commit -m "feat: add app wiring, error contract, ingredients and settings API"
```

---

### Task 5: Recipes API

**Files:**
- Create: `backend/app/routers/recipes.py`
- Modify: `backend/app/schemas.py` (append recipe schemas)
- Modify: `backend/app/main.py` (register the router)
- Modify: `backend/tests/test_ingredients_api.py` (drop the `RECIPES_LAND_IN_TASK_5` marker)
- Test: `backend/tests/test_recipes_api.py`

**Interfaces:**
- Consumes: `app.services.units.to_canonical`, `UnitError`, `CONVERSIONS`; `app.errors.AppError`; `app.models.Recipe`, `RecipeIngredient`, `Ingredient`, `PlannedMeal`, `MealPlan`, `PlanStatus`.
- Produces:
  - `RecipeLineIn(ingredient_id, quantity, display_unit, prep_note)`
  - `RecipeLineOut` adding `id`, `ingredient_name`, `ingredient_unit`, `category`, `display_quantity`, `position`
  - `RecipeIn`, `RecipePatch`, `RecipeOut`, `RecipeSummary`
  - Routes: `GET/POST /api/recipes`, `GET/PATCH/DELETE /api/recipes/{id}`

`display_quantity` on the way out is the stored canonical quantity converted
back into `display_unit`, so a recipe entered as "1 kg chicken" reads back as
"1 kg" rather than "1000 g".

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_recipes_api.py`:

```python
import pytest

PLANS_LAND_IN_TASK_6 = pytest.mark.xfail(
    reason="plans router lands in Task 6", strict=True
)


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


@pytest.fixture
def chicken(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Chicken thigh", "category": "meat_seafood", "unit": "g"},
    ).json()


def make_recipe(client, lines, **overrides):
    payload = {
        "name": "Chili",
        "serves": 4,
        "instructions": "Simmer.",
        "source_url": None,
        "notes": None,
        "lines": lines,
    }
    payload.update(overrides)
    return client.post("/api/recipes", json=payload)


def test_create_stores_lines_in_canonical_units(client, chicken):
    response = make_recipe(
        client, [{"ingredient_id": chicken["id"], "quantity": 1, "display_unit": "kg"}]
    )
    assert response.status_code == 201
    line = response.json()["lines"][0]
    assert line["quantity"] == 1000.0
    assert line["display_unit"] == "kg"
    assert line["display_quantity"] == 1.0
    assert line["ingredient_name"] == "Chicken thigh"


def test_create_rejects_a_unit_outside_the_ingredient_family(client, onion):
    response = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 200, "display_unit": "g"}]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unit_mismatch"


def test_create_rejects_an_unknown_ingredient(client):
    response = make_recipe(
        client, [{"ingredient_id": 999, "quantity": 1, "display_unit": "count"}]
    )
    assert response.status_code == 422
    assert response.json()["code"] == "ingredient_not_found"


def test_create_rejects_a_duplicate_ingredient_line(client, onion):
    response = make_recipe(
        client,
        [
            {"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"},
            {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"},
        ],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "duplicate_line"


def test_lines_keep_their_order(client, onion, chicken):
    response = make_recipe(
        client,
        [
            {"ingredient_id": chicken["id"], "quantity": 500, "display_unit": "g"},
            {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"},
        ],
    )
    names = [line["ingredient_name"] for line in response.json()["lines"]]
    assert names == ["Chicken thigh", "Onion"]


def test_patch_replaces_the_line_set_wholesale(client, onion, chicken):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    response = client.patch(
        f"/api/recipes/{recipe_id}",
        json={
            "lines": [
                {"ingredient_id": chicken["id"], "quantity": 300, "display_unit": "g"}
            ]
        },
    )
    lines = response.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["ingredient_name"] == "Chicken thigh"


def test_patch_without_lines_leaves_them_alone(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    response = client.patch(f"/api/recipes/{recipe_id}", json={"serves": 8})
    assert response.json()["serves"] == 8
    assert len(response.json()["lines"]) == 1


def test_list_returns_summaries_and_supports_search(client, onion):
    line = [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    make_recipe(client, line)
    make_recipe(client, line, name="Soup")
    results = client.get("/api/recipes", params={"q": "chi"}).json()
    assert [r["name"] for r in results] == ["Chili"]
    assert results[0]["line_count"] == 1


def test_delete_removes_an_unplanned_recipe(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    assert client.delete(f"/api/recipes/{recipe_id}").status_code == 204
    assert client.get(f"/api/recipes/{recipe_id}").status_code == 404


@PLANS_LAND_IN_TASK_6
def test_delete_is_refused_while_an_active_plan_uses_it(client, onion):
    recipe_id = make_recipe(
        client, [{"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}]
    ).json()["id"]
    plan_id = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()["id"]
    client.post(
        f"/api/plans/{plan_id}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": recipe_id, "kind": "cook"},
    )
    response = client.delete(f"/api/recipes/{recipe_id}")
    assert response.status_code == 409
    assert response.json()["code"] == "recipe_in_use"
    assert "2026-08-17" in response.json()["detail"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_recipes_api.py -v`

Expected: every test fails with 404 — `/api/recipes` does not exist yet.

- [ ] **Step 3: Append the recipe schemas**

Append to `backend/app/schemas.py`:

```python
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
```

- [ ] **Step 4: Implement the recipes router**

Create `backend/app/routers/recipes.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import (
    Ingredient,
    MealPlan,
    PlanStatus,
    PlannedMeal,
    Recipe,
    RecipeIngredient,
)
from app.schemas import (
    RecipeIn,
    RecipeLineIn,
    RecipeLineOut,
    RecipeOut,
    RecipePatch,
    RecipeSummary,
)
from app.services.units import CONVERSIONS, UnitError, to_canonical

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _get_or_404(session: Session, recipe_id: int) -> Recipe:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise AppError(404, "recipe_not_found", f"No recipe {recipe_id}")
    return recipe


def _validate_lines(
    session: Session, lines: list[RecipeLineIn]
) -> list[tuple[RecipeLineIn, float]]:
    """Resolve each line's ingredient and convert its quantity to canonical."""
    seen: set[int] = set()
    resolved: list[tuple[RecipeLineIn, float]] = []
    for line in lines:
        if line.ingredient_id in seen:
            raise AppError(
                422,
                "duplicate_line",
                f"Ingredient {line.ingredient_id} appears more than once",
            )
        seen.add(line.ingredient_id)

        ingredient = session.get(Ingredient, line.ingredient_id)
        if ingredient is None:
            raise AppError(
                422, "ingredient_not_found", f"No ingredient {line.ingredient_id}"
            )
        try:
            canonical = to_canonical(
                line.quantity, line.display_unit, ingredient.unit.value
            )
        except UnitError as exc:
            raise AppError(422, "unit_mismatch", str(exc)) from None
        resolved.append((line, canonical))
    return resolved


def _replace_lines(session: Session, recipe: Recipe, lines: list[RecipeLineIn]) -> None:
    resolved = _validate_lines(session, lines)
    recipe.lines.clear()
    session.flush()
    for position, (line, canonical) in enumerate(resolved):
        recipe.lines.append(
            RecipeIngredient(
                ingredient_id=line.ingredient_id,
                quantity=canonical,
                display_unit=line.display_unit,
                prep_note=line.prep_note,
                position=position,
            )
        )


def _line_out(session: Session, line: RecipeIngredient) -> RecipeLineOut:
    ingredient = session.get(Ingredient, line.ingredient_id)
    factor = CONVERSIONS[line.display_unit][1]
    return RecipeLineOut(
        id=line.id,
        ingredient_id=line.ingredient_id,
        ingredient_name=ingredient.name,
        ingredient_unit=ingredient.unit,
        category=ingredient.category,
        quantity=line.quantity,
        display_quantity=round(line.quantity / factor, 4),
        display_unit=line.display_unit,
        prep_note=line.prep_note,
        position=line.position,
    )


def _to_out(session: Session, recipe: Recipe) -> RecipeOut:
    return RecipeOut(
        id=recipe.id,
        name=recipe.name,
        serves=recipe.serves,
        instructions=recipe.instructions,
        source_url=recipe.source_url,
        notes=recipe.notes,
        lines=[_line_out(session, line) for line in recipe.lines],
    )


@router.get("", response_model=list[RecipeSummary])
def list_recipes(
    q: str | None = Query(default=None), session: Session = Depends(get_session)
) -> list[RecipeSummary]:
    statement = select(Recipe)
    if q:
        statement = statement.where(Recipe.name.ilike(f"%{q}%"))
    recipes = session.exec(statement.order_by(func.lower(Recipe.name))).all()
    return [
        RecipeSummary(id=r.id, name=r.name, serves=r.serves, line_count=len(r.lines))
        for r in recipes
    ]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeIn, session: Session = Depends(get_session)
) -> RecipeOut:
    recipe = Recipe(
        name=payload.name.strip(),
        serves=payload.serves,
        instructions=payload.instructions,
        source_url=payload.source_url,
        notes=payload.notes,
    )
    session.add(recipe)
    _replace_lines(session, recipe, payload.lines)
    session.commit()
    session.refresh(recipe)
    return _to_out(session, recipe)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, session: Session = Depends(get_session)) -> RecipeOut:
    return _to_out(session, _get_or_404(session, recipe_id))


@router.patch("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int, payload: RecipePatch, session: Session = Depends(get_session)
) -> RecipeOut:
    recipe = _get_or_404(session, recipe_id)
    changes = payload.model_dump(exclude_unset=True)
    lines = changes.pop("lines", None)

    for key, value in changes.items():
        setattr(recipe, key, value)
    if lines is not None:
        _replace_lines(session, recipe, [RecipeLineIn(**line) for line in lines])
    recipe.updated_at = datetime.now(timezone.utc)

    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return _to_out(session, recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, session: Session = Depends(get_session)) -> Response:
    recipe = _get_or_404(session, recipe_id)
    weeks = list(
        session.exec(
            select(MealPlan.week_start)
            .join(PlannedMeal, PlannedMeal.plan_id == MealPlan.id)
            .where(PlannedMeal.recipe_id == recipe_id)
            .where(MealPlan.status != PlanStatus.DONE)
            .distinct()
        )
    )
    if weeks:
        listed = ", ".join(str(week) for week in weeks)
        raise AppError(
            409, "recipe_in_use", f"Can't delete {recipe.name}: planned for {listed}"
        )
    session.delete(recipe)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, change the import to
`from app.routers import ingredients, recipes, settings` and add
`app.include_router(recipes.router)` beneath the ingredients line.

- [ ] **Step 6: Drop the satisfied xfail marker**

In `backend/tests/test_ingredients_api.py`, delete the three
`@RECIPES_LAND_IN_TASK_5` decorators and the constant that defines them.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -v`

Expected: PASS, with only `test_delete_is_refused_while_an_active_plan_uses_it`
reported as `xfail`.

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add recipes API with per-ingredient unit validation"
```

---

### Task 6: Meal plans and planned meals API

**Files:**
- Create: `backend/app/routers/plans.py`
- Modify: `backend/app/schemas.py` (append plan schemas)
- Modify: `backend/app/main.py` (register the router)
- Modify: `backend/tests/test_recipes_api.py` (drop the `PLANS_LAND_IN_TASK_6` marker)
- Test: `backend/tests/test_plans_api.py`

**Interfaces:**
- Consumes: `app.errors.AppError`; `app.models.MealPlan`, `PlannedMeal`, `Recipe`, `MealKind`, `MealSlot`, `PlanStatus`, `Setting`; `app.routers.settings.get_or_create`.
- Produces:
  - `SLOT_ORDER: list[MealSlot]` and `slot_index(day: int, slot: MealSlot) -> int` in `app/routers/plans.py`
  - `PlanIn(week_start: date)`, `PlanSummary(id, week_start, status, meal_count, has_list)`
  - `MealIn(day, slot, recipe_id, kind, servings_to_make, servings_eaten, source_meal_id)`
  - `MealPatch(servings_to_make, servings_eaten, kind, source_meal_id, recipe_id)`
  - `MealOut(id, day, slot, recipe_id, recipe_name, recipe_serves, kind, servings_to_make, servings_eaten, source_meal_id)`
  - `SlotWarning(meal_id: int, message: str)`
  - `PlanOut(id, week_start, status, meals: list[MealOut], warnings: list[SlotWarning])`
  - Routes: `GET/POST /api/plans`, `GET/DELETE /api/plans/{id}`, `POST /api/plans/{id}/meals`, `PATCH/DELETE /api/meals/{id}`

`slot_index` gives a single comparable position for "earlier in the week":
`day * 3 + SLOT_ORDER.index(slot)`. A leftover meal must sit strictly after
its source.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_plans_api.py`:

```python
import pytest


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


@pytest.fixture
def chili(client, onion):
    return client.post(
        "/api/recipes",
        json={
            "name": "Chili",
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}
            ],
        },
    ).json()


@pytest.fixture
def plan(client):
    return client.post("/api/plans", json={"week_start": "2026-08-17"}).json()


def add_meal(client, plan_id, **overrides):
    payload = {"day": 0, "slot": "dinner", "recipe_id": None, "kind": "cook"}
    payload.update(overrides)
    return client.post(f"/api/plans/{plan_id}/meals", json=payload)


def test_create_plan_defaults_to_planning(client):
    response = client.post("/api/plans", json={"week_start": "2026-08-17"})
    assert response.status_code == 201
    assert response.json()["status"] == "planning"
    assert response.json()["meals"] == []


def test_create_plan_rejects_a_duplicate_week(client, plan):
    response = client.post("/api/plans", json={"week_start": "2026-08-17"})
    assert response.status_code == 409
    assert response.json()["code"] == "plan_exists"


def test_create_plan_rejects_a_week_start_that_is_not_monday(client):
    response = client.post("/api/plans", json={"week_start": "2026-08-19"})
    assert response.status_code == 422
    assert response.json()["code"] == "not_monday"


def test_cook_meal_defaults_servings_to_the_recipe_yield(client, plan, chili):
    response = add_meal(client, plan["id"], recipe_id=chili["id"])
    assert response.status_code == 201
    meal = response.json()
    assert meal["servings_to_make"] == 4
    assert meal["recipe_name"] == "Chili"


def test_cook_meal_defaults_servings_eaten_to_household_size(client, plan, chili):
    client.patch("/api/settings", json={"household_size": 3})
    meal = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    assert meal["servings_eaten"] == 3


def test_a_slot_can_hold_only_one_meal(client, plan, chili):
    add_meal(client, plan["id"], recipe_id=chili["id"])
    response = add_meal(client, plan["id"], recipe_id=chili["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "slot_taken"


def test_leftovers_must_reference_a_source(client, plan, chili):
    response = add_meal(
        client, plan["id"], day=1, slot="lunch", recipe_id=chili["id"], kind="leftovers"
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_need_source"


def test_leftovers_accept_an_earlier_cook_of_the_same_recipe(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 201
    assert response.json()["servings_to_make"] is None


def test_leftovers_are_rejected_before_their_source(client, plan, chili):
    cook = add_meal(client, plan["id"], day=3, recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_before_source"


def test_leftovers_are_rejected_for_a_different_recipe(client, plan, chili, onion):
    soup = client.post(
        "/api/recipes",
        json={
            "name": "Soup",
            "serves": 2,
            "instructions": "Boil.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"}
            ],
        },
    ).json()
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    response = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=soup["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_recipe_mismatch"


def test_leftovers_are_rejected_when_the_source_is_itself_leftovers(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    first = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    ).json()
    response = add_meal(
        client,
        plan["id"],
        day=2,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=first["id"],
    )
    assert response.status_code == 422
    assert response.json()["code"] == "leftovers_source_not_cook"


def test_no_warning_when_the_batch_covers_every_serving(client, plan, chili):
    # serves 4, household 2: cook eats 2, one leftover slot eats 2. Exactly 4.
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    assert client.get(f"/api/plans/{plan['id']}").json()["warnings"] == []


def test_warning_when_leftovers_outrun_the_batch(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    for day, slot in ((1, "lunch"), (2, "lunch")):
        add_meal(
            client,
            plan["id"],
            day=day,
            slot=slot,
            recipe_id=chili["id"],
            kind="leftovers",
            source_meal_id=cook["id"],
        )
    warnings = client.get(f"/api/plans/{plan['id']}").json()["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["meal_id"] == cook["id"]
    assert "6" in warnings[0]["message"] and "4" in warnings[0]["message"]


def test_patching_servings_to_make_clears_the_warning(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    for day, slot in ((1, "lunch"), (2, "lunch")):
        add_meal(
            client,
            plan["id"],
            day=day,
            slot=slot,
            recipe_id=chili["id"],
            kind="leftovers",
            source_meal_id=cook["id"],
        )
    client.patch(f"/api/meals/{cook['id']}", json={"servings_to_make": 6})
    assert client.get(f"/api/plans/{plan['id']}").json()["warnings"] == []


def test_deleting_a_cook_meal_with_leftovers_is_refused(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    )
    response = client.delete(f"/api/meals/{cook['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "meal_has_leftovers"


def test_deleting_a_leftover_meal_succeeds(client, plan, chili):
    cook = add_meal(client, plan["id"], recipe_id=chili["id"]).json()
    leftover = add_meal(
        client,
        plan["id"],
        day=1,
        slot="lunch",
        recipe_id=chili["id"],
        kind="leftovers",
        source_meal_id=cook["id"],
    ).json()
    assert client.delete(f"/api/meals/{leftover['id']}").status_code == 204
    assert len(client.get(f"/api/plans/{plan['id']}").json()["meals"]) == 1


def test_plan_list_is_newest_first(client):
    client.post("/api/plans", json={"week_start": "2026-08-10"})
    client.post("/api/plans", json={"week_start": "2026-08-17"})
    weeks = [p["week_start"] for p in client.get("/api/plans").json()]
    assert weeks == ["2026-08-17", "2026-08-10"]


def test_deleting_a_plan_removes_its_meals(client, plan, chili):
    add_meal(client, plan["id"], recipe_id=chili["id"])
    assert client.delete(f"/api/plans/{plan['id']}").status_code == 204
    assert client.get(f"/api/plans/{plan['id']}").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_plans_api.py -v`

Expected: every test fails with 404 — `/api/plans` does not exist yet.

- [ ] **Step 3: Append the plan schemas**

Append to `backend/app/schemas.py`:

```python
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
```

- [ ] **Step 4: Implement the plans router**

Create `backend/app/routers/plans.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import (
    MealKind,
    MealPlan,
    MealSlot,
    PlannedMeal,
    Recipe,
    ShoppingList,
)
from app.routers.settings import get_or_create as get_settings
from app.schemas import (
    MealIn,
    MealOut,
    MealPatch,
    PlanIn,
    PlanOut,
    PlanSummary,
    SlotWarning,
)

router = APIRouter(prefix="/api", tags=["plans"])

SLOT_ORDER: list[MealSlot] = [MealSlot.BREAKFAST, MealSlot.LUNCH, MealSlot.DINNER]


def slot_index(day: int, slot: MealSlot) -> int:
    """A single comparable position in the week, so 'earlier' is well defined."""
    return day * len(SLOT_ORDER) + SLOT_ORDER.index(slot)


def _plan_or_404(session: Session, plan_id: int) -> MealPlan:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        raise AppError(404, "plan_not_found", f"No plan {plan_id}")
    return plan


def _meal_or_404(session: Session, meal_id: int) -> PlannedMeal:
    meal = session.get(PlannedMeal, meal_id)
    if meal is None:
        raise AppError(404, "meal_not_found", f"No meal {meal_id}")
    return meal


def _recipe_or_422(session: Session, recipe_id: int) -> Recipe:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise AppError(422, "recipe_not_found", f"No recipe {recipe_id}")
    return recipe


def _meal_out(session: Session, meal: PlannedMeal) -> MealOut:
    recipe = session.get(Recipe, meal.recipe_id)
    return MealOut(
        id=meal.id,
        day=meal.day,
        slot=meal.slot,
        recipe_id=meal.recipe_id,
        recipe_name=recipe.name,
        recipe_serves=recipe.serves,
        kind=meal.kind,
        servings_to_make=meal.servings_to_make,
        servings_eaten=meal.servings_eaten,
        source_meal_id=meal.source_meal_id,
    )


def _warnings(meals: list[PlannedMeal]) -> list[SlotWarning]:
    """Flag cook meals whose batch does not cover everything eating from it."""
    by_id = {meal.id: meal for meal in meals}
    demand: dict[int, int] = {
        meal.id: meal.servings_eaten for meal in meals if meal.kind is MealKind.COOK
    }
    for meal in meals:
        if meal.kind is MealKind.LEFTOVERS and meal.source_meal_id in demand:
            demand[meal.source_meal_id] += meal.servings_eaten

    warnings: list[SlotWarning] = []
    for meal_id, eaten in demand.items():
        made = by_id[meal_id].servings_to_make or 0
        if eaten > made:
            warnings.append(
                SlotWarning(
                    meal_id=meal_id,
                    message=(
                        f"Planned meals eat {eaten} servings but this batch "
                        f"makes {made}. Raise the batch or drop a leftover slot."
                    ),
                )
            )
    return sorted(warnings, key=lambda w: w.meal_id)


def _plan_out(session: Session, plan: MealPlan) -> PlanOut:
    meals = sorted(plan.meals, key=lambda m: slot_index(m.day, m.slot))
    return PlanOut(
        id=plan.id,
        week_start=plan.week_start,
        status=plan.status,
        meals=[_meal_out(session, meal) for meal in meals],
        warnings=_warnings(meals),
    )


@router.get("/plans", response_model=list[PlanSummary])
def list_plans(session: Session = Depends(get_session)) -> list[PlanSummary]:
    plans = session.exec(select(MealPlan).order_by(MealPlan.week_start.desc())).all()
    return [
        PlanSummary(
            id=plan.id,
            week_start=plan.week_start,
            status=plan.status,
            meal_count=len(plan.meals),
            has_list=session.exec(
                select(ShoppingList).where(ShoppingList.plan_id == plan.id)
            ).first()
            is not None,
        )
        for plan in plans
    ]


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(payload: PlanIn, session: Session = Depends(get_session)) -> PlanOut:
    if payload.week_start.weekday() != 0:
        raise AppError(
            422, "not_monday", f"{payload.week_start} is not a Monday"
        )
    existing = session.exec(
        select(MealPlan).where(MealPlan.week_start == payload.week_start)
    ).first()
    if existing is not None:
        raise AppError(
            409, "plan_exists", f"A plan for {payload.week_start} already exists"
        )
    plan = MealPlan(week_start=payload.week_start)
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return _plan_out(session, plan)


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, session: Session = Depends(get_session)) -> PlanOut:
    return _plan_out(session, _plan_or_404(session, plan_id))


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: int, session: Session = Depends(get_session)) -> Response:
    plan = _plan_or_404(session, plan_id)
    session.delete(plan)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _validate_leftovers(
    session: Session, plan: MealPlan, day: int, slot: MealSlot,
    recipe_id: int, source_meal_id: int | None,
) -> None:
    if source_meal_id is None:
        raise AppError(
            422,
            "leftovers_need_source",
            "A leftovers meal must reference the meal it was cooked in",
        )
    source = session.get(PlannedMeal, source_meal_id)
    if source is None or source.plan_id != plan.id:
        raise AppError(
            422, "leftovers_source_not_found", f"No meal {source_meal_id} in this plan"
        )
    if source.kind is not MealKind.COOK:
        raise AppError(
            422, "leftovers_source_not_cook", "Leftovers must point at a cooked meal"
        )
    if source.recipe_id != recipe_id:
        raise AppError(
            422,
            "leftovers_recipe_mismatch",
            "Leftovers must be of the same recipe as their source",
        )
    if slot_index(day, slot) <= slot_index(source.day, source.slot):
        raise AppError(
            422,
            "leftovers_before_source",
            "Leftovers must come after the meal they were cooked in",
        )


@router.post(
    "/plans/{plan_id}/meals", response_model=MealOut, status_code=status.HTTP_201_CREATED
)
def add_meal(
    plan_id: int, payload: MealIn, session: Session = Depends(get_session)
) -> MealOut:
    plan = _plan_or_404(session, plan_id)
    recipe = _recipe_or_422(session, payload.recipe_id)

    taken = session.exec(
        select(PlannedMeal)
        .where(PlannedMeal.plan_id == plan_id)
        .where(PlannedMeal.day == payload.day)
        .where(PlannedMeal.slot == payload.slot)
    ).first()
    if taken is not None:
        raise AppError(
            409, "slot_taken", f"Day {payload.day} {payload.slot.value} already has a meal"
        )

    if payload.kind is MealKind.LEFTOVERS:
        _validate_leftovers(
            session, plan, payload.day, payload.slot, payload.recipe_id,
            payload.source_meal_id,
        )
        servings_to_make = None
        source_meal_id = payload.source_meal_id
    else:
        servings_to_make = payload.servings_to_make or recipe.serves
        source_meal_id = None

    meal = PlannedMeal(
        plan_id=plan_id,
        day=payload.day,
        slot=payload.slot,
        recipe_id=payload.recipe_id,
        kind=payload.kind,
        servings_to_make=servings_to_make,
        servings_eaten=payload.servings_eaten or get_settings(session).household_size,
        source_meal_id=source_meal_id,
    )
    session.add(meal)
    session.commit()
    session.refresh(meal)
    return _meal_out(session, meal)


@router.patch("/meals/{meal_id}", response_model=MealOut)
def update_meal(
    meal_id: int, payload: MealPatch, session: Session = Depends(get_session)
) -> MealOut:
    meal = _meal_or_404(session, meal_id)
    changes = payload.model_dump(exclude_unset=True)

    kind = changes.get("kind", meal.kind)
    recipe_id = changes.get("recipe_id", meal.recipe_id)
    source_meal_id = changes.get("source_meal_id", meal.source_meal_id)

    if kind is MealKind.LEFTOVERS:
        _validate_leftovers(
            session, meal.plan, meal.day, meal.slot, recipe_id, source_meal_id
        )
        changes["servings_to_make"] = None
    else:
        changes["source_meal_id"] = None
        if changes.get("servings_to_make") is None and meal.servings_to_make is None:
            changes["servings_to_make"] = _recipe_or_422(session, recipe_id).serves

    for key, value in changes.items():
        setattr(meal, key, value)
    session.add(meal)
    session.commit()
    session.refresh(meal)
    return _meal_out(session, meal)


@router.delete("/meals/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(meal_id: int, session: Session = Depends(get_session)) -> Response:
    meal = _meal_or_404(session, meal_id)
    dependents = session.exec(
        select(PlannedMeal).where(PlannedMeal.source_meal_id == meal_id)
    ).all()
    if dependents:
        raise AppError(
            409,
            "meal_has_leftovers",
            "Remove the leftover slots that point at this meal first",
        )
    session.delete(meal)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Register the router**

In `backend/app/main.py`, import `plans` alongside the others and add
`app.include_router(plans.router)`.

- [ ] **Step 6: Drop the satisfied xfail marker**

In `backend/tests/test_recipes_api.py`, delete the `@PLANS_LAND_IN_TASK_6`
decorator and the constant that defines it.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -v`

Expected: PASS, no xfails remaining.

- [ ] **Step 8: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add meal plan API with leftover validation and batch warnings"
```

---

### Task 7: Shopping list persistence, regeneration, and API

The regeneration merge rules are the part users notice when they break, so
they get their own test module against the service directly, plus API tests
for the routes.

**Files:**
- Create: `backend/app/services/list_service.py`
- Create: `backend/app/routers/lists.py`
- Modify: `backend/app/schemas.py` (append list schemas)
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_list_service.py`, `backend/tests/test_lists_api.py`

**Interfaces:**
- Consumes: `app.services.list_builder.build_draft`, `CookMeal`, `IngredientRef`, `RecipeLine`, `RecipeRef`; `app.models` tables and enums; `app.errors.AppError`.
- Produces:
  - `list_service.generate(session: Session, plan_id: int) -> ShoppingList` — creates the list if absent, otherwise regenerates it in place under the merge rules
  - `ListItemIn(custom_name: str | None, ingredient_id: int | None, quantity: float | None, display_unit: str | None, note: str | None)`
  - `ListItemPatch(checked: bool | None, quantity: float | None, display_unit: str | None, note: str | None, custom_name: str | None)`
  - `ListItemOut(id, ingredient_id, name, category, quantity, display_quantity, display_unit, source, section, checked, note, contributions)`
  - `ListOut(id, plan_id, week_start, generated_at, finalized_at, items: list[ListItemOut])`
  - `ListSummary(id, plan_id, week_start, finalized_at, item_count, checked_count)`
  - Routes: `GET /api/plans/{id}/list`, `POST /api/plans/{id}/list`, `POST /api/lists/{id}/items`, `PATCH/DELETE /api/lists/{id}/items/{item_id}`, `POST /api/lists/{id}/finalize`, `GET /api/lists`, `GET /api/lists/{id}`

**Merge rules implemented by `generate`, restated so the implementer does not
have to cross-reference the spec:**

1. Items whose `source` is `manual` or `suggested` are never touched or removed.
2. Recipe-derived items are recomputed from the current plan.
3. If a recomputed item's `ingredient_id` matches an existing recipe-derived
   item, that row is updated in place — quantity, display, section, and
   contributions change; `checked` and `note` are preserved even when the
   quantity changed.
4. A recipe-derived item with no contributing recipe any more is deleted, even
   if it was checked.

- [ ] **Step 1: Write the failing service tests**

Create `backend/tests/test_list_service.py`:

```python
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

    plan = MealPlan(week_start="2026-08-17")
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
            plan_id=plan.id, day=1, slot=MealSlot.LUNCH, recipe_id=chili.id,
            kind=MealKind.LEFTOVERS, servings_eaten=2, source_meal_id=cook.id,
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

    for meal in list(session.exec(select(PlannedMeal))):
        session.delete(meal)
    session.commit()

    regenerated = generate(session, world["plan"].id)
    assert regenerated.items == []


def test_regenerating_keeps_a_manual_item_even_with_no_meals(session, world):
    shopping_list = generate(session, world["plan"].id)
    session.add(
        ShoppingListItem(
            list_id=shopping_list.id, custom_name="Coffee",
            source=ItemSource.MANUAL, section=ItemSection.BUY,
        )
    )
    session.commit()
    for meal in list(session.exec(select(PlannedMeal))):
        session.delete(meal)
    session.commit()

    regenerated = generate(session, world["plan"].id)
    assert [i.custom_name for i in regenerated.items] == ["Coffee"]
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_list_service.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.list_service'`.

- [ ] **Step 3: Implement the list service**

Create `backend/app/services/list_service.py`:

```python
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
        session.commit()
        session.refresh(shopping_list)

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
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_list_service.py -v`

Expected: PASS, 8 tests.

- [ ] **Step 5: Write the failing API tests**

Create `backend/tests/test_lists_api.py`:

```python
import pytest


@pytest.fixture
def world(client):
    onion = client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()
    chili = client.post(
        "/api/recipes",
        json={
            "name": "Chili",
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}
            ],
        },
    ).json()
    plan = client.post("/api/plans", json={"week_start": "2026-08-17"}).json()
    client.post(
        f"/api/plans/{plan['id']}/meals",
        json={"day": 0, "slot": "dinner", "recipe_id": chili["id"], "kind": "cook"},
    )
    return {"onion": onion, "chili": chili, "plan": plan}


def test_get_before_generating_is_404(client, world):
    response = client.get(f"/api/plans/{world['plan']['id']}/list")
    assert response.status_code == 404
    assert response.json()["code"] == "list_not_found"


def test_post_generates_the_list_and_moves_the_plan_to_shopping(client, world):
    response = client.post(f"/api/plans/{world['plan']['id']}/list")
    assert response.status_code == 201
    body = response.json()
    assert body["week_start"] == "2026-08-17"
    assert [i["name"] for i in body["items"]] == ["Onion"]
    assert body["items"][0]["display_quantity"] == 2.0
    assert body["items"][0]["category"] == "produce"
    plan = client.get(f"/api/plans/{world['plan']['id']}").json()
    assert plan["status"] == "shopping"


def test_contributions_explain_each_line(client, world):
    body = client.post(f"/api/plans/{world['plan']['id']}/list").json()
    assert body["items"][0]["contributions"][0]["recipe_name"] == "Chili"


def test_manual_items_can_be_added_and_checked(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    added = client.post(
        f"/api/lists/{list_id}/items", json={"custom_name": "Paper towels"}
    )
    assert added.status_code == 201
    assert added.json()["source"] == "manual"

    item_id = added.json()["id"]
    patched = client.patch(
        f"/api/lists/{list_id}/items/{item_id}", json={"checked": True}
    )
    assert patched.json()["checked"] is True


def test_a_manual_item_needs_a_name_or_an_ingredient(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    response = client.post(f"/api/lists/{list_id}/items", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "item_needs_name"


def test_manual_items_can_be_deleted(client, world):
    list_id = client.post(f"/api/plans/{world['plan']['id']}/list").json()["id"]
    item_id = client.post(
        f"/api/lists/{list_id}/items", json={"custom_name": "Coffee"}
    ).json()["id"]
    assert client.delete(f"/api/lists/{list_id}/items/{item_id}").status_code == 204
    names = [i["name"] for i in client.get(f"/api/lists/{list_id}").json()["items"]]
    assert "Coffee" not in names


def test_regenerating_after_a_plan_change_updates_quantities(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    meal_id = client.get(f"/api/plans/{plan_id}").json()["meals"][0]["id"]
    client.patch(f"/api/meals/{meal_id}", json={"servings_to_make": 8})

    body = client.post(f"/api/plans/{plan_id}/list").json()
    assert body["id"] == list_id
    assert body["items"][0]["display_quantity"] == 4.0


def test_finalize_marks_the_list_and_the_plan_done(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    response = client.post(f"/api/lists/{list_id}/finalize")
    assert response.status_code == 200
    assert response.json()["finalized_at"] is not None
    assert client.get(f"/api/plans/{plan_id}").json()["status"] == "done"


def test_history_lists_only_finalized_lists(client, world):
    plan_id = world["plan"]["id"]
    list_id = client.post(f"/api/plans/{plan_id}/list").json()["id"]
    assert client.get("/api/lists").json() == []
    client.post(f"/api/lists/{list_id}/finalize")
    history = client.get("/api/lists").json()
    assert len(history) == 1
    assert history[0]["week_start"] == "2026-08-17"
    assert history[0]["item_count"] == 1
    assert history[0]["checked_count"] == 0
```

- [ ] **Step 6: Run the API tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_lists_api.py -v`

Expected: failures with 404 — the list routes do not exist yet.

- [ ] **Step 7: Append the list schemas**

Append to `backend/app/schemas.py`:

```python
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
```

- [ ] **Step 8: Implement the lists router**

Create `backend/app/routers/lists.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status
from sqlmodel import Session, select

from app.db import get_session
from app.errors import AppError
from app.models import (
    CATEGORY_ORDER,
    Ingredient,
    ItemSection,
    ItemSource,
    MealPlan,
    PlanStatus,
    ShoppingList,
    ShoppingListItem,
)
from app.schemas import ListItemIn, ListItemOut, ListItemPatch, ListOut, ListSummary
from app.services.list_service import generate
from app.services.units import CONVERSIONS, UnitError, format_display, to_canonical

router = APIRouter(prefix="/api", tags=["lists"])

_CATEGORY_RANK = {category: rank for rank, category in enumerate(CATEGORY_ORDER)}


def _list_or_404(session: Session, list_id: int) -> ShoppingList:
    shopping_list = session.get(ShoppingList, list_id)
    if shopping_list is None:
        raise AppError(404, "list_not_found", f"No list {list_id}")
    return shopping_list


def _item_out(session: Session, item: ShoppingListItem) -> ListItemOut:
    ingredient = (
        session.get(Ingredient, item.ingredient_id)
        if item.ingredient_id is not None
        else None
    )
    return ListItemOut(
        id=item.id,
        ingredient_id=item.ingredient_id,
        name=ingredient.name if ingredient else (item.custom_name or ""),
        category=ingredient.category if ingredient else None,
        quantity=item.quantity,
        display_quantity=item.display_quantity,
        display_unit=item.display_unit,
        source=item.source,
        section=item.section,
        checked=item.checked,
        note=item.note,
        contributions=item.contributions or [],
    )


def _sorted_items(session: Session, shopping_list: ShoppingList) -> list[ListItemOut]:
    out = [_item_out(session, item) for item in shopping_list.items]

    def key(item: ListItemOut) -> tuple[int, int, str]:
        section_rank = 1 if item.section is ItemSection.STAPLE_CHECK else 0
        # Free-text items have no category; park them with `other`.
        category_rank = (
            _CATEGORY_RANK[item.category] if item.category else len(CATEGORY_ORDER)
        )
        return (section_rank, category_rank, item.name.lower())

    return sorted(out, key=key)


def _list_out(session: Session, shopping_list: ShoppingList) -> ListOut:
    plan = session.get(MealPlan, shopping_list.plan_id)
    return ListOut(
        id=shopping_list.id,
        plan_id=shopping_list.plan_id,
        week_start=plan.week_start,
        generated_at=shopping_list.generated_at,
        finalized_at=shopping_list.finalized_at,
        items=_sorted_items(session, shopping_list),
    )


@router.get("/plans/{plan_id}/list", response_model=ListOut)
def read_list(plan_id: int, session: Session = Depends(get_session)) -> ListOut:
    shopping_list = session.exec(
        select(ShoppingList).where(ShoppingList.plan_id == plan_id)
    ).first()
    if shopping_list is None:
        raise AppError(404, "list_not_found", f"Plan {plan_id} has no list yet")
    return _list_out(session, shopping_list)


@router.post(
    "/plans/{plan_id}/list", response_model=ListOut, status_code=status.HTTP_201_CREATED
)
def generate_list(plan_id: int, session: Session = Depends(get_session)) -> ListOut:
    plan = session.get(MealPlan, plan_id)
    if plan is None:
        raise AppError(404, "plan_not_found", f"No plan {plan_id}")
    shopping_list = generate(session, plan_id)
    if plan.status is PlanStatus.PLANNING:
        plan.status = PlanStatus.SHOPPING
        session.add(plan)
        session.commit()
    return _list_out(session, shopping_list)


@router.post(
    "/lists/{list_id}/items",
    response_model=ListItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    list_id: int, payload: ListItemIn, session: Session = Depends(get_session)
) -> ListItemOut:
    shopping_list = _list_or_404(session, list_id)
    if payload.ingredient_id is None and not (payload.custom_name or "").strip():
        raise AppError(
            422, "item_needs_name", "Give the item a name or pick an ingredient"
        )

    quantity = display_quantity = None
    display_unit = payload.display_unit
    if payload.ingredient_id is not None:
        ingredient = session.get(Ingredient, payload.ingredient_id)
        if ingredient is None:
            raise AppError(
                422, "ingredient_not_found", f"No ingredient {payload.ingredient_id}"
            )
        if payload.quantity is not None:
            try:
                quantity = to_canonical(
                    payload.quantity,
                    payload.display_unit or ingredient.unit.value,
                    ingredient.unit.value,
                )
            except UnitError as exc:
                raise AppError(422, "unit_mismatch", str(exc)) from None
            display_quantity, display_unit = format_display(
                quantity, ingredient.unit.value
            )

    item = ShoppingListItem(
        list_id=shopping_list.id,
        ingredient_id=payload.ingredient_id,
        custom_name=(payload.custom_name or "").strip() or None,
        quantity=quantity,
        display_quantity=display_quantity,
        display_unit=display_unit,
        source=ItemSource.MANUAL,
        section=ItemSection.BUY,
        note=payload.note,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_out(session, item)


@router.patch("/lists/{list_id}/items/{item_id}", response_model=ListItemOut)
def update_item(
    list_id: int,
    item_id: int,
    payload: ListItemPatch,
    session: Session = Depends(get_session),
) -> ListItemOut:
    _list_or_404(session, list_id)
    item = session.get(ShoppingListItem, item_id)
    if item is None or item.list_id != list_id:
        raise AppError(404, "item_not_found", f"No item {item_id} on list {list_id}")

    changes = payload.model_dump(exclude_unset=True)
    if "quantity" in changes and item.ingredient_id is not None:
        ingredient = session.get(Ingredient, item.ingredient_id)
        unit = changes.get("display_unit") or item.display_unit or ingredient.unit.value
        try:
            canonical = to_canonical(changes["quantity"], unit, ingredient.unit.value)
        except UnitError as exc:
            raise AppError(422, "unit_mismatch", str(exc)) from None
        changes["quantity"] = canonical
        changes["display_quantity"] = round(canonical / CONVERSIONS[unit][1], 4)
        changes["display_unit"] = unit

    for key, value in changes.items():
        setattr(item, key, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_out(session, item)


@router.delete(
    "/lists/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_item(
    list_id: int, item_id: int, session: Session = Depends(get_session)
) -> Response:
    _list_or_404(session, list_id)
    item = session.get(ShoppingListItem, item_id)
    if item is None or item.list_id != list_id:
        raise AppError(404, "item_not_found", f"No item {item_id} on list {list_id}")
    session.delete(item)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/lists/{list_id}/finalize", response_model=ListOut)
def finalize(list_id: int, session: Session = Depends(get_session)) -> ListOut:
    shopping_list = _list_or_404(session, list_id)
    shopping_list.finalized_at = datetime.now(timezone.utc)
    plan = session.get(MealPlan, shopping_list.plan_id)
    plan.status = PlanStatus.DONE
    session.add(shopping_list)
    session.add(plan)
    session.commit()
    session.refresh(shopping_list)
    return _list_out(session, shopping_list)


@router.get("/lists", response_model=list[ListSummary])
def list_history(session: Session = Depends(get_session)) -> list[ListSummary]:
    lists = session.exec(
        select(ShoppingList)
        .where(ShoppingList.finalized_at.is_not(None))
        .order_by(ShoppingList.finalized_at.desc())
    ).all()
    summaries = []
    for shopping_list in lists:
        plan = session.get(MealPlan, shopping_list.plan_id)
        summaries.append(
            ListSummary(
                id=shopping_list.id,
                plan_id=shopping_list.plan_id,
                week_start=plan.week_start,
                finalized_at=shopping_list.finalized_at,
                item_count=len(shopping_list.items),
                checked_count=sum(1 for i in shopping_list.items if i.checked),
            )
        )
    return summaries


@router.get("/lists/{list_id}", response_model=ListOut)
def read_list_by_id(list_id: int, session: Session = Depends(get_session)) -> ListOut:
    return _list_out(session, _list_or_404(session, list_id))
```

- [ ] **Step 9: Register the router**

In `backend/app/main.py`, import `lists` and add `app.include_router(lists.router)`.

- [ ] **Step 10: Run the whole suite to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -v`

Expected: PASS, all tests.

- [ ] **Step 11: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add shopping list generation, regeneration, and list API"
```

---

### Task 8: Repeat-buy suggestions

**Files:**
- Create: `backend/app/services/suggestions.py`
- Modify: `backend/app/schemas.py` (append `SuggestionOut`)
- Modify: `backend/app/routers/lists.py` (add the route)
- Test: `backend/tests/test_suggestions.py`

**Interfaces:**
- Consumes: `app.models.ShoppingList`, `ShoppingListItem`, `ItemSource`, `Ingredient`.
- Produces:
  - `HISTORY_WINDOW = 4`, `APPEARANCE_THRESHOLD = 3`
  - `item_key(ingredient_id: int | None, custom_name: str | None) -> str` — `"i:{id}"` or `"n:{normalized name}"`
  - `suggest(session: Session, list_id: int) -> list[SuggestionOut]`
  - Route: `GET /api/lists/{list_id}/suggestions`
  - `SuggestionOut(ingredient_id: int | None, name: str, times_bought: int)`

Suggestions look only at `manual` items on the most recent `HISTORY_WINDOW`
finalized lists, excluding the list being suggested for. An item qualifying on
`APPEARANCE_THRESHOLD` or more of them is offered. Anything already on the
current list is filtered out. Nothing is ever added automatically.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_suggestions.py`:

```python
import pytest

WEEKS = [
    "2026-06-01",
    "2026-06-08",
    "2026-06-15",
    "2026-06-22",
    "2026-06-29",
]


@pytest.fixture
def onion(client):
    return client.post(
        "/api/ingredients",
        json={"name": "Onion", "category": "produce", "unit": "count"},
    ).json()


def finished_week(client, week, manual_names):
    """Create a plan with no meals, add manual items, and finalize its list."""
    plan = client.post("/api/plans", json={"week_start": week}).json()
    list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
    for name in manual_names:
        client.post(f"/api/lists/{list_id}/items", json={"custom_name": name})
    client.post(f"/api/lists/{list_id}/finalize")
    return list_id


def open_week(client, week):
    plan = client.post("/api/plans", json={"week_start": week}).json()
    return client.post(f"/api/plans/{plan['id']}/list").json()["id"]


def suggestions(client, list_id):
    return client.get(f"/api/lists/{list_id}/suggestions").json()


def test_an_item_bought_three_of_four_weeks_is_suggested(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[3], ["Bananas"])
    current = open_week(client, WEEKS[4])
    assert [s["name"] for s in suggestions(client, current)] == ["Coffee"]


def test_times_bought_is_reported(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[3], ["Coffee"])
    current = open_week(client, WEEKS[4])
    assert suggestions(client, current)[0]["times_bought"] == 4


def test_an_item_bought_twice_is_not_suggested(client):
    for week in WEEKS[:2]:
        finished_week(client, week, ["Coffee"])
    finished_week(client, WEEKS[2], [])
    finished_week(client, WEEKS[3], [])
    current = open_week(client, WEEKS[4])
    assert suggestions(client, current) == []


def test_only_the_last_four_finalized_lists_count(client):
    finished_week(client, WEEKS[0], ["Coffee"])
    for week in WEEKS[1:4]:
        finished_week(client, week, ["Coffee"])
    # A fifth, more recent week without coffee pushes the oldest out of range,
    # leaving three of four - still enough.
    finished_week(client, WEEKS[4], [])
    current = open_week(client, "2026-07-06")
    assert [s["name"] for s in suggestions(client, current)] == ["Coffee"]


def test_matching_is_case_and_whitespace_insensitive(client):
    finished_week(client, WEEKS[0], ["Coffee"])
    finished_week(client, WEEKS[1], ["  coffee "])
    finished_week(client, WEEKS[2], ["COFFEE"])
    current = open_week(client, WEEKS[3])
    assert len(suggestions(client, current)) == 1


def test_an_item_already_on_the_current_list_is_not_suggested(client):
    for week in WEEKS[:3]:
        finished_week(client, week, ["Coffee"])
    current = open_week(client, WEEKS[3])
    client.post(f"/api/lists/{current}/items", json={"custom_name": "coffee"})
    assert suggestions(client, current) == []


def test_recipe_items_are_never_suggested(client, onion):
    chili = client.post(
        "/api/recipes",
        json={
            "name": "Chili",
            "serves": 4,
            "instructions": "Simmer.",
            "lines": [
                {"ingredient_id": onion["id"], "quantity": 2, "display_unit": "count"}
            ],
        },
    ).json()
    for week in WEEKS[:3]:
        plan = client.post("/api/plans", json={"week_start": week}).json()
        client.post(
            f"/api/plans/{plan['id']}/meals",
            json={"day": 0, "slot": "dinner", "recipe_id": chili["id"], "kind": "cook"},
        )
        list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
        client.post(f"/api/lists/{list_id}/finalize")
    current = open_week(client, WEEKS[3])
    assert suggestions(client, current) == []


def test_ingredient_backed_manual_items_are_suggested_by_ingredient(client, onion):
    for week in WEEKS[:3]:
        plan = client.post("/api/plans", json={"week_start": week}).json()
        list_id = client.post(f"/api/plans/{plan['id']}/list").json()["id"]
        client.post(
            f"/api/lists/{list_id}/items",
            json={"ingredient_id": onion["id"], "quantity": 1, "display_unit": "count"},
        )
        client.post(f"/api/lists/{list_id}/finalize")
    current = open_week(client, WEEKS[3])
    result = suggestions(client, current)
    assert result[0]["ingredient_id"] == onion["id"]
    assert result[0]["name"] == "Onion"


def test_no_history_produces_no_suggestions(client):
    current = open_week(client, WEEKS[0])
    assert suggestions(client, current) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_suggestions.py -v`

Expected: failures with 404 — the suggestions route does not exist yet.

- [ ] **Step 3: Append the schema**

Append to `backend/app/schemas.py`:

```python
class SuggestionOut(BaseModel):
    ingredient_id: Optional[int]
    name: str
    times_bought: int
```

- [ ] **Step 4: Implement the suggestions service**

Create `backend/app/services/suggestions.py`:

```python
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
```

- [ ] **Step 5: Add the route**

Append to `backend/app/routers/lists.py`:

```python
from app.schemas import SuggestionOut
from app.services.suggestions import suggest


@router.get("/lists/{list_id}/suggestions", response_model=list[SuggestionOut])
def read_suggestions(
    list_id: int, session: Session = Depends(get_session)
) -> list[SuggestionOut]:
    _list_or_404(session, list_id)
    return suggest(session, list_id)
```

Move the two new imports up to the existing import block rather than leaving
them at the bottom of the file.

- [ ] **Step 6: Run the whole suite to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -v`

Expected: PASS, all tests. The backend is now feature-complete.

- [ ] **Step 7: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: add repeat-buy suggestions from finalized list history"
```

---

### Task 9: Frontend scaffold, types, API client, and app shell

Scaffolding, the typed client, the shell, the dev script, and the README are
one deliverable: the first thing a reviewer can actually run end to end.

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/vitest.config.ts`, `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/styles.css`
- Create: `frontend/src/types/index.ts`, `frontend/src/api/client.ts`, `frontend/src/api/hooks.ts`
- Create: `frontend/src/components/Layout.tsx`, `frontend/src/components/Toast.tsx`
- Create: `dev.ps1`, `README.md`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: the backend routes from Tasks 4–8.
- Produces:
  - `types/index.ts`: `Category`, `CanonicalUnit`, `PlanStatus`, `MealSlot`, `MealKind`, `ItemSource`, `ItemSection`, `Ingredient`, `RecipeLine`, `Recipe`, `RecipeSummary`, `Meal`, `SlotWarning`, `Plan`, `PlanSummary`, `ListItem`, `ShoppingList`, `ListSummary`, `Suggestion`, `Settings`, `ApiError`
  - `api/client.ts`: `class ApiError extends Error` with `code: string`; `request<T>(path, init?): Promise<T>`; and named functions `getIngredients`, `createIngredient`, `updateIngredient`, `deleteIngredient`, `getRecipes`, `getRecipe`, `createRecipe`, `updateRecipe`, `deleteRecipe`, `getPlans`, `getPlan`, `createPlan`, `deletePlan`, `addMeal`, `updateMeal`, `deleteMeal`, `getList`, `generateList`, `addListItem`, `updateListItem`, `deleteListItem`, `finalizeList`, `getListHistory`, `getListById`, `getSuggestions`, `getSettings`, `updateSettings`
  - `api/hooks.ts`: `keys`, the TanStack Query wrappers `useIngredients`, `useRecipes`, `useRecipe`, `usePlans`, `usePlan`, `useList`, `useListById`, `useListHistory`, `useSuggestions`, `useSettings`, and `useInvalidatingMutation(mutationFn, invalidate)`
  - `components/Toast.tsx`: `ToastProvider`, `useToast() -> { showError(err: unknown): void, showMessage(text: string): void }`
  - `CATEGORY_LABELS: Record<Category, string>` and `UNIT_FAMILIES: Record<CanonicalUnit, string[]>` in `types/index.ts`

`UNIT_FAMILIES` mirrors the backend's `CONVERSIONS` table and is what the
recipe editor uses to constrain the unit dropdown:
`count: ["count"]`, `g: ["g", "kg", "oz", "lb"]`, `ml: ["ml", "l", "tsp", "tbsp", "cup"]`.

- [ ] **Step 1: Scaffold the Vite project**

From the repository root:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install @tanstack/react-query react-router-dom
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

Then delete the template files you will not use: `src/App.css`,
`src/assets/`, and the contents of `src/index.css`.

- [ ] **Step 2: Configure Vite to proxy the API**

Replace `frontend/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
```

Create `frontend/vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/setupTests.ts'],
  },
})
```

Create `frontend/src/setupTests.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

Add to the `scripts` block of `frontend/package.json`:

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 3: Write the failing test**

Create `frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, createIngredient, getIngredients, request } from './client'

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('returns the parsed body on success', async () => {
    mockFetch(200, { ok: true })
    await expect(request('/api/health')).resolves.toEqual({ ok: true })
  })

  it('throws an ApiError carrying the code and detail', async () => {
    mockFetch(409, { detail: "Can't delete Onion: used by Chili", code: 'ingredient_in_use' })
    const error = await request('/api/ingredients/1').catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('ingredient_in_use')
    expect((error as ApiError).message).toBe("Can't delete Onion: used by Chili")
  })

  it('falls back to a generic message when the body has no detail', async () => {
    mockFetch(500, {})
    const error = await request('/api/health').catch((e) => e)
    expect((error as ApiError).code).toBe('unknown')
    expect((error as ApiError).message).toContain('500')
  })

  it('returns undefined for a 204', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 } as Response)
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/api/ingredients/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})

describe('endpoint helpers', () => {
  it('passes a search term as a query parameter', async () => {
    const fetchMock = mockFetch(200, [])
    await getIngredients('oni')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ingredients?q=oni')
  })

  it('omits the query parameter when there is no search term', async () => {
    const fetchMock = mockFetch(200, [])
    await getIngredients()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/ingredients')
  })

  it('posts JSON with the right content type', async () => {
    const fetchMock = mockFetch(201, { id: 1 })
    await createIngredient({ name: 'Onion', category: 'produce', unit: 'count' })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body as string).name).toBe('Onion')
  })
})
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm test`

Expected: FAIL — `Failed to resolve import "./client"`.

- [ ] **Step 5: Write the shared types**

Create `frontend/src/types/index.ts`:

```ts
export type Category =
  | 'produce'
  | 'bakery'
  | 'meat_seafood'
  | 'dairy'
  | 'frozen'
  | 'dry_goods'
  | 'seasoning'
  | 'other'

export type CanonicalUnit = 'count' | 'g' | 'ml'
export type PlanStatus = 'planning' | 'shopping' | 'done'
export type MealSlot = 'breakfast' | 'lunch' | 'dinner'
export type MealKind = 'cook' | 'leftovers'
export type ItemSource = 'recipe' | 'manual' | 'suggested'
export type ItemSection = 'buy' | 'staple_check'

/** Store-walk order, matching the backend's CATEGORY_ORDER. */
export const CATEGORY_ORDER: Category[] = [
  'produce',
  'bakery',
  'meat_seafood',
  'dairy',
  'frozen',
  'dry_goods',
  'seasoning',
  'other',
]

export const CATEGORY_LABELS: Record<Category, string> = {
  produce: 'Produce',
  bakery: 'Bakery',
  meat_seafood: 'Meat & seafood',
  dairy: 'Dairy',
  frozen: 'Frozen',
  dry_goods: 'Dry goods',
  seasoning: 'Seasonings',
  other: 'Other',
}

/** Which entry units are legal for an ingredient, keyed by its canonical unit. */
export const UNIT_FAMILIES: Record<CanonicalUnit, string[]> = {
  count: ['count'],
  g: ['g', 'kg', 'oz', 'lb'],
  ml: ['ml', 'l', 'tsp', 'tbsp', 'cup'],
}

export const DEFAULT_UNIT_FOR_CATEGORY: Record<Category, CanonicalUnit> = {
  produce: 'count',
  bakery: 'count',
  meat_seafood: 'g',
  dairy: 'ml',
  frozen: 'g',
  dry_goods: 'g',
  seasoning: 'ml',
  other: 'count',
}

export const SLOTS: MealSlot[] = ['breakfast', 'lunch', 'dinner']
export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export interface Ingredient {
  id: number
  name: string
  category: Category
  unit: CanonicalUnit
  is_staple: boolean
  usage_count: number
}

export interface RecipeLine {
  id: number
  ingredient_id: number
  ingredient_name: string
  ingredient_unit: CanonicalUnit
  category: Category
  quantity: number
  display_quantity: number
  display_unit: string
  prep_note: string | null
  position: number
}

export interface Recipe {
  id: number
  name: string
  serves: number
  instructions: string
  source_url: string | null
  notes: string | null
  lines: RecipeLine[]
}

export interface RecipeSummary {
  id: number
  name: string
  serves: number
  line_count: number
}

export interface RecipeLineInput {
  ingredient_id: number
  quantity: number
  display_unit: string
  prep_note?: string | null
}

export interface Meal {
  id: number
  day: number
  slot: MealSlot
  recipe_id: number
  recipe_name: string
  recipe_serves: number
  kind: MealKind
  servings_to_make: number | null
  servings_eaten: number
  source_meal_id: number | null
}

export interface SlotWarning {
  meal_id: number
  message: string
}

export interface Plan {
  id: number
  week_start: string
  status: PlanStatus
  meals: Meal[]
  warnings: SlotWarning[]
}

export interface PlanSummary {
  id: number
  week_start: string
  status: PlanStatus
  meal_count: number
  has_list: boolean
}

export interface Contribution {
  recipe_id: number
  recipe_name: string
  quantity: number
}

export interface ListItem {
  id: number
  ingredient_id: number | null
  name: string
  category: Category | null
  quantity: number | null
  display_quantity: number | null
  display_unit: string | null
  source: ItemSource
  section: ItemSection
  checked: boolean
  note: string | null
  contributions: Contribution[]
}

export interface ShoppingList {
  id: number
  plan_id: number
  week_start: string
  generated_at: string
  finalized_at: string | null
  items: ListItem[]
}

export interface ListSummary {
  id: number
  plan_id: number
  week_start: string
  finalized_at: string | null
  item_count: number
  checked_count: number
}

export interface Suggestion {
  ingredient_id: number | null
  name: string
  times_bought: number
}

export interface Settings {
  household_size: number
}
```

- [ ] **Step 6: Write the API client**

Create `frontend/src/api/client.ts`:

```ts
import type {
  CanonicalUnit,
  Category,
  Ingredient,
  ListItem,
  ListSummary,
  MealKind,
  MealSlot,
  Plan,
  PlanSummary,
  Recipe,
  RecipeLineInput,
  RecipeSummary,
  Settings,
  ShoppingList,
  Suggestion,
} from '../types'

/** Mirrors the backend's {detail, code} error contract. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (response.status === 204) return undefined as T
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(
      body.detail ?? `Request failed with status ${response.status}`,
      body.code ?? 'unknown',
      response.status,
    )
  }
  return (await response.json()) as T
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function remove(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' })
}

function withQuery(path: string, q?: string): string {
  return q ? `${path}?q=${encodeURIComponent(q)}` : path
}

// Ingredients
export const getIngredients = (q?: string) =>
  request<Ingredient[]>(withQuery('/api/ingredients', q))
export const createIngredient = (body: {
  name: string
  category: Category
  unit: CanonicalUnit
  is_staple?: boolean
}) => post<Ingredient>('/api/ingredients', body)
export const updateIngredient = (
  id: number,
  body: Partial<{ name: string; category: Category; unit: CanonicalUnit; is_staple: boolean }>,
) => patch<Ingredient>(`/api/ingredients/${id}`, body)
export const deleteIngredient = (id: number) => remove(`/api/ingredients/${id}`)

// Recipes
export const getRecipes = (q?: string) => request<RecipeSummary[]>(withQuery('/api/recipes', q))
export const getRecipe = (id: number) => request<Recipe>(`/api/recipes/${id}`)
export const createRecipe = (body: {
  name: string
  serves: number
  instructions: string
  source_url?: string | null
  notes?: string | null
  lines: RecipeLineInput[]
}) => post<Recipe>('/api/recipes', body)
export const updateRecipe = (
  id: number,
  body: Partial<{
    name: string
    serves: number
    instructions: string
    source_url: string | null
    notes: string | null
    lines: RecipeLineInput[]
  }>,
) => patch<Recipe>(`/api/recipes/${id}`, body)
export const deleteRecipe = (id: number) => remove(`/api/recipes/${id}`)

// Plans and meals
export const getPlans = () => request<PlanSummary[]>('/api/plans')
export const getPlan = (id: number) => request<Plan>(`/api/plans/${id}`)
export const createPlan = (weekStart: string) => post<Plan>('/api/plans', { week_start: weekStart })
export const deletePlan = (id: number) => remove(`/api/plans/${id}`)
export const addMeal = (
  planId: number,
  body: {
    day: number
    slot: MealSlot
    recipe_id: number
    kind: MealKind
    servings_to_make?: number | null
    servings_eaten?: number | null
    source_meal_id?: number | null
  },
) => post(`/api/plans/${planId}/meals`, body)
export const updateMeal = (
  mealId: number,
  body: Partial<{ servings_to_make: number; servings_eaten: number }>,
) => patch(`/api/meals/${mealId}`, body)
export const deleteMeal = (mealId: number) => remove(`/api/meals/${mealId}`)

// Shopping lists
export const getList = (planId: number) => request<ShoppingList>(`/api/plans/${planId}/list`)
export const generateList = (planId: number) => post<ShoppingList>(`/api/plans/${planId}/list`)
export const addListItem = (
  listId: number,
  body: {
    custom_name?: string | null
    ingredient_id?: number | null
    quantity?: number | null
    display_unit?: string | null
    note?: string | null
  },
) => post<ListItem>(`/api/lists/${listId}/items`, body)
export const updateListItem = (
  listId: number,
  itemId: number,
  body: Partial<{ checked: boolean; quantity: number; display_unit: string; note: string }>,
) => patch<ListItem>(`/api/lists/${listId}/items/${itemId}`, body)
export const deleteListItem = (listId: number, itemId: number) =>
  remove(`/api/lists/${listId}/items/${itemId}`)
export const finalizeList = (listId: number) => post<ShoppingList>(`/api/lists/${listId}/finalize`)
export const getListHistory = () => request<ListSummary[]>('/api/lists')
export const getListById = (listId: number) => request<ShoppingList>(`/api/lists/${listId}`)
export const getSuggestions = (listId: number) =>
  request<Suggestion[]>(`/api/lists/${listId}/suggestions`)

// Settings
export const getSettings = () => request<Settings>('/api/settings')
export const updateSettings = (householdSize: number) =>
  patch<Settings>('/api/settings', { household_size: householdSize })
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `cd frontend && npm test`

Expected: PASS, 7 tests.

- [ ] **Step 8: Write the query hooks**

Create `frontend/src/api/hooks.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './client'

export const keys = {
  ingredients: (q?: string) => ['ingredients', q ?? ''] as const,
  recipes: (q?: string) => ['recipes', q ?? ''] as const,
  recipe: (id: number) => ['recipe', id] as const,
  plans: () => ['plans'] as const,
  plan: (id: number) => ['plan', id] as const,
  list: (planId: number) => ['list', planId] as const,
  listById: (id: number) => ['listById', id] as const,
  history: () => ['history'] as const,
  suggestions: (listId: number) => ['suggestions', listId] as const,
  settings: () => ['settings'] as const,
}

export const useIngredients = (q?: string) =>
  useQuery({ queryKey: keys.ingredients(q), queryFn: () => api.getIngredients(q) })
export const useRecipes = (q?: string) =>
  useQuery({ queryKey: keys.recipes(q), queryFn: () => api.getRecipes(q) })
export const useRecipe = (id: number | undefined) =>
  useQuery({ queryKey: keys.recipe(id!), queryFn: () => api.getRecipe(id!), enabled: id != null })
export const usePlans = () => useQuery({ queryKey: keys.plans(), queryFn: api.getPlans })
export const usePlan = (id: number | undefined) =>
  useQuery({ queryKey: keys.plan(id!), queryFn: () => api.getPlan(id!), enabled: id != null })
export const useList = (planId: number | undefined) =>
  useQuery({
    queryKey: keys.list(planId!),
    queryFn: () => api.getList(planId!),
    enabled: planId != null,
    retry: false,
  })
export const useListHistory = () => useQuery({ queryKey: keys.history(), queryFn: api.getListHistory })
export const useListById = (id: number | undefined) =>
  useQuery({ queryKey: keys.listById(id!), queryFn: () => api.getListById(id!), enabled: id != null })
export const useSuggestions = (listId: number | undefined) =>
  useQuery({
    queryKey: keys.suggestions(listId!),
    queryFn: () => api.getSuggestions(listId!),
    enabled: listId != null,
  })
export const useSettings = () => useQuery({ queryKey: keys.settings(), queryFn: api.getSettings })

/** Wraps a mutation so it invalidates the given key prefixes on success. */
export function useInvalidatingMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
  invalidate: readonly (readonly unknown[])[],
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      invalidate.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
    },
  })
}
```

- [ ] **Step 9: Build the app shell**

Create `frontend/src/components/Toast.tsx`:

```tsx
import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'

interface ToastValue {
  showError: (error: unknown) => void
  showMessage: (text: string) => void
}

const ToastContext = createContext<ToastValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<{ id: number; text: string; kind: string }[]>([])

  const push = useCallback((text: string, kind: string) => {
    const id = Date.now() + Math.random()
    setMessages((current) => [...current, { id, text, kind }])
    setTimeout(() => setMessages((current) => current.filter((m) => m.id !== id)), 6000)
  }, [])

  const value = useMemo<ToastValue>(
    () => ({
      showError: (error) =>
        push(error instanceof ApiError ? error.message : 'Something went wrong', 'error'),
      showMessage: (text) => push(text, 'info'),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} className={`toast toast--${m.kind}`}>
            {m.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastValue {
  const value = useContext(ToastContext)
  if (!value) throw new Error('useToast must be used inside a ToastProvider')
  return value
}
```

Create `frontend/src/components/Layout.tsx`:

```tsx
import { NavLink, Outlet } from 'react-router-dom'

const LINKS = [
  { to: '/planner', label: 'Planner' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
  { to: '/history', label: 'History' },
]

export function Layout() {
  return (
    <div className="layout">
      <nav className="nav">
        <span className="nav__brand">RatKitchen</span>
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
```

Create `frontend/src/App.tsx`. Later tasks replace each `Placeholder` with the
real page:

```tsx
import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'

function Placeholder({ name }: { name: string }) {
  return <p>{name} lands in a later task.</p>
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/planner" replace />} />
        <Route path="planner" element={<Placeholder name="Planner" />} />
        <Route path="planner/:planId" element={<Placeholder name="Planner" />} />
        <Route path="recipes" element={<Placeholder name="Recipes" />} />
        <Route path="recipes/new" element={<Placeholder name="Recipe editor" />} />
        <Route path="recipes/:recipeId" element={<Placeholder name="Recipe editor" />} />
        <Route path="ingredients" element={<Placeholder name="Ingredients" />} />
        <Route path="list/:planId" element={<Placeholder name="Shopping list" />} />
        <Route path="history" element={<Placeholder name="History" />} />
        <Route path="history/:listId" element={<Placeholder name="Archived list" />} />
      </Route>
    </Routes>
  )
}
```

Replace `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { ToastProvider } from './components/Toast'
import './styles.css'
import './print.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <App />
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
```

Create `frontend/src/styles.css` with a plain, readable desktop baseline:

```css
:root {
  --bg: #fbfaf7;
  --surface: #ffffff;
  --border: #d9d5cc;
  --text: #23211d;
  --muted: #6b6659;
  --accent: #2f6f4f;
  --warn: #b07d17;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  color: var(--text);
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); }

.layout { max-width: 1100px; margin: 0 auto; padding: 0 24px 64px; }
.nav { display: flex; align-items: baseline; gap: 20px; padding: 20px 0; border-bottom: 1px solid var(--border); }
.nav__brand { font-weight: 700; margin-right: 12px; }
.nav__link { color: var(--muted); text-decoration: none; }
.nav__link--active { color: var(--accent); font-weight: 600; }
.content { padding-top: 24px; }

button { font: inherit; padding: 6px 12px; border: 1px solid var(--border); background: var(--surface); border-radius: 6px; cursor: pointer; }
button:hover { border-color: var(--accent); }
button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
input, select, textarea { font: inherit; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }

table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; font-size: 0.9em; }

.badge--warn { color: var(--warn); }
.muted { color: var(--muted); }

.toasts { position: fixed; right: 20px; bottom: 20px; display: flex; flex-direction: column; gap: 8px; }
.toast { padding: 10px 14px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 2px 8px rgb(0 0 0 / 0.08); max-width: 360px; }
.toast--error { border-color: #b3261e; color: #b3261e; }
```

Create an empty `frontend/src/print.css` for now; Task 14 fills it in.

- [ ] **Step 10: Write the dev script and README**

Create `dev.ps1` at the repository root:

```powershell
# Starts the FastAPI backend and the Vite dev server together.
# Ctrl+C stops both.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$backend = Start-Process -PassThru -NoNewWindow -FilePath 'pwsh' -ArgumentList @(
  '-NoProfile', '-Command',
  "Set-Location '$root/backend'; .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)
$frontend = Start-Process -PassThru -NoNewWindow -FilePath 'pwsh' -ArgumentList @(
  '-NoProfile', '-Command',
  "Set-Location '$root/frontend'; npm run dev"
)

Write-Host 'RatKitchen running. API on http://127.0.0.1:8000, UI on http://127.0.0.1:5173'
try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  foreach ($p in @($backend, $frontend)) {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
}
```

Create `README.md`:

````markdown
# RatKitchen

A local recipe manager and weekly shopping list generator. Plan a week of
meals, get one accurate aisle-grouped list, print it, shop once.

## Setup

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cd ../frontend
npm install
```

## Running

```powershell
./dev.ps1
```

The UI is at http://127.0.0.1:5173 and the API at http://127.0.0.1:8000.
API docs are at http://127.0.0.1:8000/docs.

## Tests

```powershell
cd backend; .venv/Scripts/python -m pytest
cd frontend; npm test
```

## How it works

An ingredient's unit is fixed when you create it — produce is counted, meat and
dry goods are weighed. Every recipe using that ingredient must use that unit,
so the shopping list can sum across recipes without guessing. Quantities always
round up. Seasonings are flagged as staples: recipes still record how much you
need, but the list shows them as a "check your rack" reminder rather than
adding teaspoons together.
````

- [ ] **Step 11: Verify the app runs**

Run `./dev.ps1`, open http://127.0.0.1:5173, and confirm the nav renders and
`/planner` shows its placeholder. Stop with Ctrl+C.

- [ ] **Step 12: Commit**

```bash
git add frontend dev.ps1 README.md
git commit -m "feat: add frontend scaffold, typed API client, and app shell"
```

---

### Task 10: Ingredients page

The catalog manager, and the escape hatch for fixing a mis-categorized
ingredient. Straight CRUD over an endpoint already covered by backend tests, so
verification here is manual rather than another test suite.

**Files:**
- Create: `frontend/src/pages/Ingredients/IngredientsPage.tsx`
- Create: `frontend/src/pages/Ingredients/NewIngredientForm.tsx`
- Modify: `frontend/src/App.tsx` (swap in the real route)
- Modify: `frontend/src/styles.css` (append the rules below)

**Interfaces:**
- Consumes: `useIngredients`, `useInvalidatingMutation`, `keys` from `api/hooks`; `createIngredient`, `updateIngredient`, `deleteIngredient` from `api/client`; `useToast`; `CATEGORY_ORDER`, `CATEGORY_LABELS`, `DEFAULT_UNIT_FOR_CATEGORY`, `UNIT_FAMILIES` from `types`.
- Produces:
  - `IngredientsPage` (default page component)
  - `NewIngredientForm({ onCreated, initialName }: { onCreated?: (i: Ingredient) => void; initialName?: string })` — reused by the recipe editor in Task 11, which is why it is its own component

- [ ] **Step 1: Build the reusable create form**

Create `frontend/src/pages/Ingredients/NewIngredientForm.tsx`:

```tsx
import { useState } from 'react'
import { createIngredient } from '../../api/client'
import { keys, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import {
  CATEGORY_LABELS,
  CATEGORY_ORDER,
  DEFAULT_UNIT_FOR_CATEGORY,
} from '../../types'
import type { CanonicalUnit, Category, Ingredient } from '../../types'

const UNITS: { value: CanonicalUnit; label: string }[] = [
  { value: 'count', label: 'count (whole items)' },
  { value: 'g', label: 'grams (weight)' },
  { value: 'ml', label: 'millilitres (volume)' },
]

interface Props {
  initialName?: string
  onCreated?: (ingredient: Ingredient) => void
  onCancel?: () => void
}

export function NewIngredientForm({ initialName = '', onCreated, onCancel }: Props) {
  const [name, setName] = useState(initialName)
  const [category, setCategory] = useState<Category>('produce')
  const [unit, setUnit] = useState<CanonicalUnit>(DEFAULT_UNIT_FOR_CATEGORY.produce)
  const [unitTouched, setUnitTouched] = useState(false)
  const [isStaple, setIsStaple] = useState(false)
  const [stapleTouched, setStapleTouched] = useState(false)
  const toast = useToast()

  const create = useInvalidatingMutation(createIngredient, [keys.ingredients()])

  // The category drives the unit and staple defaults until the user overrides them.
  function pickCategory(next: Category) {
    setCategory(next)
    if (!unitTouched) setUnit(DEFAULT_UNIT_FOR_CATEGORY[next])
    if (!stapleTouched) setIsStaple(next === 'seasoning')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      const ingredient = await create.mutateAsync({
        name: name.trim(),
        category,
        unit,
        is_staple: isStaple,
      })
      setName('')
      onCreated?.(ingredient)
    } catch (error) {
      toast.showError(error)
    }
  }

  return (
    <form className="ingredient-form" aria-label="New ingredient" onSubmit={submit}>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label>
        Category
        <select value={category} onChange={(e) => pickCategory(e.target.value as Category)}>
          {CATEGORY_ORDER.map((c) => (
            <option key={c} value={c}>
              {CATEGORY_LABELS[c]}
            </option>
          ))}
        </select>
      </label>
      <label>
        Unit
        <select
          value={unit}
          onChange={(e) => {
            setUnitTouched(true)
            setUnit(e.target.value as CanonicalUnit)
          }}
        >
          {UNITS.map((u) => (
            <option key={u.value} value={u.value}>
              {u.label}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={isStaple}
          onChange={(e) => {
            setStapleTouched(true)
            setIsStaple(e.target.checked)
          }}
        />
        Staple (reminder only, no quantity on the list)
      </label>
      <div className="ingredient-form__actions">
        <button className="primary" type="submit" disabled={create.isPending}>
          Add ingredient
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}
```

- [ ] **Step 2: Build the page**

Create `frontend/src/pages/Ingredients/IngredientsPage.tsx`:

```tsx
import { useState } from 'react'
import { deleteIngredient, updateIngredient } from '../../api/client'
import { keys, useIngredients, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { CATEGORY_LABELS, CATEGORY_ORDER } from '../../types'
import type { Category, Ingredient } from '../../types'
import { NewIngredientForm } from './NewIngredientForm'

export function IngredientsPage() {
  const [search, setSearch] = useState('')
  const { data: ingredients = [], isLoading } = useIngredients(search || undefined)
  const toast = useToast()

  const update = useInvalidatingMutation(
    ({ id, body }: { id: number; body: Parameters<typeof updateIngredient>[1] }) =>
      updateIngredient(id, body),
    [keys.ingredients(), keys.ingredients(search)],
  )
  const remove = useInvalidatingMutation(deleteIngredient, [
    keys.ingredients(),
    keys.ingredients(search),
  ])

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (error) {
      toast.showError(error)
    }
  }

  return (
    <section>
      <h1>Ingredients</h1>
      <p className="muted">
        An ingredient's unit is fixed once a recipe uses it, so the shopping list can add
        amounts together without guessing.
      </p>

      <NewIngredientForm />

      <input
        className="search"
        placeholder="Search ingredients"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Category</th>
              <th>Unit</th>
              <th>Staple</th>
              <th>Used by</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ingredients.map((ingredient: Ingredient) => (
              <tr key={ingredient.id}>
                <td>{ingredient.name}</td>
                <td>
                  <select
                    value={ingredient.category}
                    onChange={(e) =>
                      run(
                        update.mutateAsync({
                          id: ingredient.id,
                          body: { category: e.target.value as Category },
                        }),
                      )
                    }
                  >
                    {CATEGORY_ORDER.map((c) => (
                      <option key={c} value={c}>
                        {CATEGORY_LABELS[c]}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {ingredient.unit}
                  {ingredient.usage_count > 0 && (
                    <span className="muted" title="Locked because recipes use this unit">
                      {' '}
                      (locked)
                    </span>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={ingredient.is_staple}
                    onChange={(e) =>
                      run(
                        update.mutateAsync({
                          id: ingredient.id,
                          body: { is_staple: e.target.checked },
                        }),
                      )
                    }
                  />
                </td>
                <td className="muted">{ingredient.usage_count} recipes</td>
                <td>
                  <button
                    disabled={ingredient.usage_count > 0}
                    title={
                      ingredient.usage_count > 0
                        ? 'Used by a recipe — remove it there first'
                        : undefined
                    }
                    onClick={() => run(remove.mutateAsync(ingredient.id))}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
```

- [ ] **Step 3: Append the styles**

Append to `frontend/src/styles.css`:

```css
.ingredient-form { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; padding: 16px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 20px; }
.ingredient-form label { display: flex; flex-direction: column; gap: 4px; font-size: 0.9em; color: var(--muted); }
.ingredient-form label.checkbox { flex-direction: row; align-items: center; gap: 8px; }
.ingredient-form__actions { display: flex; gap: 8px; }
.search { width: 260px; margin-bottom: 12px; }
```

- [ ] **Step 4: Wire the route**

In `frontend/src/App.tsx`, import `IngredientsPage` and replace the
`ingredients` route's element with `<IngredientsPage />`.

- [ ] **Step 5: Verify by hand**

Run `./dev.ps1` and, at http://127.0.0.1:5173/ingredients:

1. Add "Onion" as produce — confirm the unit auto-selects `count`.
2. Add "Cumin" as a seasoning — confirm the unit auto-selects `ml` and the
   staple box ticks itself.
3. Search for "on" and confirm only Onion is listed.
4. Delete Onion and confirm it disappears.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: add ingredients catalog page"
```

---

### Task 11: Recipe list and recipe editor

The editor is the screen that makes or breaks the app: it is the only place a
unit is ever chosen, and it has to make creating a new ingredient painless. It
gets real tests.

**Files:**
- Create: `frontend/src/components/IngredientPicker.tsx`
- Create: `frontend/src/pages/Recipes/RecipesPage.tsx`
- Create: `frontend/src/pages/RecipeEditor/RecipeEditorPage.tsx`
- Create: `frontend/src/pages/RecipeEditor/LineRow.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`
- Test: `frontend/src/pages/RecipeEditor/RecipeEditorPage.test.tsx`

**Interfaces:**
- Consumes: `useIngredients`, `useRecipe`, `useRecipes`, `useInvalidatingMutation`, `keys`; `createRecipe`, `updateRecipe`, `deleteRecipe`; `NewIngredientForm` from Task 10; `UNIT_FAMILIES`, `CATEGORY_LABELS`.
- Produces:
  - `IngredientPicker({ value, onSelect, onCreateRequest })` — a text input with a filtered dropdown of existing ingredients and a "Create <typed name>" row when nothing matches. `value: Ingredient | null`, `onSelect: (i: Ingredient | null) => void` (null clears the choice), `onCreateRequest: (typedName: string) => void`.
  - `LineRow({ line, onChange, onRemove })` where `line: EditorLine`
  - `interface EditorLine { key: string; ingredient: Ingredient | null; quantity: string; displayUnit: string; prepNote: string }`
  - `RecipesPage`, `RecipeEditorPage`

The unit dropdown for a line is `UNIT_FAMILIES[line.ingredient.unit]`. For a
`count` ingredient that array has one entry, so the control renders as a plain
number with the word "whole" beside it rather than a dropdown.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/RecipeEditor/RecipeEditorPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/Toast'
import { RecipeEditorPage } from './RecipeEditorPage'

const ONION = {
  id: 1,
  name: 'Onion',
  category: 'produce',
  unit: 'count',
  is_staple: false,
  usage_count: 0,
}
const CHICKEN = {
  id: 2,
  name: 'Chicken thigh',
  category: 'meat_seafood',
  unit: 'g',
  is_staple: false,
  usage_count: 0,
}

let posted: any[] = []

function mockApi() {
  posted = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/ingredients') && (!init || init.method === undefined)) {
        return { ok: true, status: 200, json: async () => [ONION, CHICKEN] } as Response
      }
      if (url === '/api/ingredients' && init?.method === 'POST') {
        const body = JSON.parse(init.body as string)
        return {
          ok: true,
          status: 201,
          json: async () => ({ ...body, id: 3, usage_count: 0 }),
        } as Response
      }
      if (url === '/api/recipes' && init?.method === 'POST') {
        posted.push(JSON.parse(init.body as string))
        return { ok: true, status: 201, json: async () => ({ id: 7, lines: [] }) } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
}

function renderEditor() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/recipes/new']}>
        <ToastProvider>
          <Routes>
            <Route path="/recipes/new" element={<RecipeEditorPage />} />
            <Route path="/recipes" element={<p>Recipe list</p>} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(mockApi)
afterEach(() => vi.unstubAllGlobals())

describe('RecipeEditorPage', () => {
  it('constrains the unit choices to the selected ingredient family', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'chick')
    await user.click(await screen.findByRole('option', { name: /chicken thigh/i }))

    const unitSelect = screen.getByLabelText(/unit for chicken thigh/i)
    const options = within(unitSelect).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['g', 'kg', 'oz', 'lb'])
  })

  it('shows a plain whole-number field for a count ingredient', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'onio')
    await user.click(await screen.findByRole('option', { name: /^onion$/i }))

    expect(screen.queryByLabelText(/unit for onion/i)).not.toBeInTheDocument()
    expect(screen.getByText('whole')).toBeInTheDocument()
  })

  it('offers inline creation when the typed name matches nothing', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'Tahini')
    await user.click(await screen.findByRole('option', { name: /create "Tahini"/i }))

    expect(screen.getByRole('form', { name: /new ingredient/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/^name$/i)).toHaveValue('Tahini')
  })

  it('selects a newly created ingredient into the line it was created from', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'Tahini')
    await user.click(await screen.findByRole('option', { name: /create "Tahini"/i }))
    await user.click(screen.getByRole('button', { name: /add ingredient$/i }))

    expect(await screen.findByText('Tahini')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: /new ingredient/i })).not.toBeInTheDocument()
  })

  it('submits the typed display unit rather than a converted amount', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.type(screen.getByLabelText(/recipe name/i), 'Roast chicken')
    await user.clear(screen.getByLabelText(/serves/i))
    await user.type(screen.getByLabelText(/serves/i), '4')

    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.type(screen.getByPlaceholderText(/search ingredients/i), 'chick')
    await user.click(await screen.findByRole('option', { name: /chicken thigh/i }))
    await user.type(screen.getByLabelText(/quantity for chicken thigh/i), '1')
    await user.selectOptions(screen.getByLabelText(/unit for chicken thigh/i), 'kg')

    await user.click(screen.getByRole('button', { name: /save recipe/i }))

    expect(posted).toHaveLength(1)
    expect(posted[0].name).toBe('Roast chicken')
    expect(posted[0].serves).toBe(4)
    expect(posted[0].lines).toEqual([
      { ingredient_id: 2, quantity: 1, display_unit: 'kg', prep_note: null },
    ])
  })

  it('refuses to save a line with no ingredient chosen', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.type(screen.getByLabelText(/recipe name/i), 'Empty')
    await user.click(screen.getByRole('button', { name: /add ingredient line/i }))
    await user.click(screen.getByRole('button', { name: /save recipe/i }))

    expect(posted).toHaveLength(0)
    expect(screen.getByText(/pick an ingredient for every line/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`

Expected: FAIL — `Failed to resolve import "./RecipeEditorPage"`.

- [ ] **Step 3: Build the ingredient picker**

Create `frontend/src/components/IngredientPicker.tsx`:

```tsx
import { useState } from 'react'
import { useIngredients } from '../api/hooks'
import type { Ingredient } from '../types'

interface Props {
  value: Ingredient | null
  /** null clears the current choice and reopens the search. */
  onSelect: (ingredient: Ingredient | null) => void
  onCreateRequest: (typedName: string) => void
}

export function IngredientPicker({ value, onSelect, onCreateRequest }: Props) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const { data: ingredients = [] } = useIngredients()

  if (value) {
    return (
      <span className="picker__chosen">
        {value.name}
        <button
          type="button"
          className="link"
          onClick={() => {
            setQuery('')
            setOpen(true)
            onSelect(null)
          }}
        >
          change
        </button>
      </span>
    )
  }

  const trimmed = query.trim()
  const matches = trimmed
    ? ingredients.filter((i) => i.name.toLowerCase().includes(trimmed.toLowerCase()))
    : ingredients
  const exact = matches.some((i) => i.name.toLowerCase() === trimmed.toLowerCase())

  return (
    <div className="picker">
      <input
        placeholder="Search ingredients"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
      />
      {open && (
        <ul className="picker__menu" role="listbox">
          {matches.slice(0, 8).map((ingredient) => (
            <li key={ingredient.id}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  onSelect(ingredient)
                  setOpen(false)
                }}
              >
                {ingredient.name}
                <span className="muted"> · {ingredient.unit}</span>
              </button>
            </li>
          ))}
          {trimmed && !exact && (
            <li>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => {
                  onCreateRequest(trimmed)
                  setOpen(false)
                }}
              >
                Create "{trimmed}"
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Build the line row**

Create `frontend/src/pages/RecipeEditor/LineRow.tsx`:

```tsx
import { IngredientPicker } from '../../components/IngredientPicker'
import { UNIT_FAMILIES } from '../../types'
import type { Ingredient } from '../../types'

export interface EditorLine {
  key: string
  ingredient: Ingredient | null
  quantity: string
  displayUnit: string
  prepNote: string
}

interface Props {
  line: EditorLine
  onChange: (line: EditorLine) => void
  onRemove: () => void
  onCreateRequest: (typedName: string) => void
}

export function LineRow({ line, onChange, onRemove, onCreateRequest }: Props) {
  const units = line.ingredient ? UNIT_FAMILIES[line.ingredient.unit] : []
  const name = line.ingredient?.name ?? 'ingredient'

  return (
    <div className="line-row">
      <IngredientPicker
        value={line.ingredient}
        onSelect={(ingredient) =>
          onChange({
            ...line,
            ingredient,
            // A fresh selection resets the unit to the ingredient's canonical one.
            displayUnit: ingredient ? ingredient.unit : '',
          })
        }
        onCreateRequest={onCreateRequest}
      />

      {line.ingredient && (
        <>
          <input
            type="number"
            min="0"
            step="any"
            aria-label={`Quantity for ${name}`}
            value={line.quantity}
            onChange={(e) => onChange({ ...line, quantity: e.target.value })}
          />
          {units.length > 1 ? (
            <select
              aria-label={`Unit for ${name}`}
              value={line.displayUnit}
              onChange={(e) => onChange({ ...line, displayUnit: e.target.value })}
            >
              {units.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
          ) : (
            <span className="muted">whole</span>
          )}
          <input
            aria-label={`Prep note for ${name}`}
            placeholder="diced, boneless…"
            value={line.prepNote}
            onChange={(e) => onChange({ ...line, prepNote: e.target.value })}
          />
        </>
      )}

      <button type="button" onClick={onRemove} aria-label={`Remove ${name}`}>
        ×
      </button>
    </div>
  )
}
```

- [ ] **Step 5: Build the editor page**

Create `frontend/src/pages/RecipeEditor/RecipeEditorPage.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createRecipe, updateRecipe } from '../../api/client'
import { keys, useInvalidatingMutation, useRecipe } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { NewIngredientForm } from '../Ingredients/NewIngredientForm'
import { LineRow } from './LineRow'
import type { EditorLine } from './LineRow'
import type { Ingredient } from '../../types'

let nextKey = 0
const blankLine = (): EditorLine => ({
  key: `line-${nextKey++}`,
  ingredient: null,
  quantity: '',
  displayUnit: '',
  prepNote: '',
})

export function RecipeEditorPage() {
  const { recipeId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const id = recipeId ? Number(recipeId) : undefined
  const { data: existing } = useRecipe(id)

  const [name, setName] = useState('')
  const [serves, setServes] = useState('2')
  const [instructions, setInstructions] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [lines, setLines] = useState<EditorLine[]>([])
  const [error, setError] = useState<string | null>(null)
  // Which line asked for a new ingredient, so the created one lands in it.
  const [creatingFor, setCreatingFor] = useState<{ key: string; name: string } | null>(null)

  useEffect(() => {
    if (!existing) return
    setName(existing.name)
    setServes(String(existing.serves))
    setInstructions(existing.instructions)
    setSourceUrl(existing.source_url ?? '')
    setLines(
      existing.lines.map((line) => ({
        key: `line-${nextKey++}`,
        ingredient: {
          id: line.ingredient_id,
          name: line.ingredient_name,
          category: line.category,
          unit: line.ingredient_unit,
          is_staple: false,
          usage_count: 0,
        },
        quantity: String(line.display_quantity),
        displayUnit: line.display_unit,
        prepNote: line.prep_note ?? '',
      })),
    )
  }, [existing])

  const save = useInvalidatingMutation(
    (body: Parameters<typeof createRecipe>[0]) =>
      id ? updateRecipe(id, body) : createRecipe(body),
    [keys.recipes(), ...(id ? [keys.recipe(id)] : [])],
  )

  function updateLine(key: string, next: EditorLine) {
    setLines((current) => current.map((line) => (line.key === key ? next : line)))
  }

  function ingredientCreated(ingredient: Ingredient) {
    if (!creatingFor) return
    setLines((current) =>
      current.map((line) =>
        line.key === creatingFor.key
          ? { ...line, ingredient, displayUnit: ingredient.unit }
          : line,
      ),
    )
    setCreatingFor(null)
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (lines.some((line) => !line.ingredient)) {
      setError('Pick an ingredient for every line, or remove the empty ones.')
      return
    }
    try {
      await save.mutateAsync({
        name: name.trim(),
        serves: Number(serves),
        instructions,
        source_url: sourceUrl.trim() || null,
        lines: lines.map((line) => ({
          ingredient_id: line.ingredient!.id,
          quantity: Number(line.quantity),
          display_unit: line.displayUnit,
          prep_note: line.prepNote.trim() || null,
        })),
      })
      navigate('/recipes')
    } catch (err) {
      toast.showError(err)
    }
  }

  return (
    <section>
      <h1>{id ? 'Edit recipe' : 'New recipe'}</h1>
      <form onSubmit={submit} className="recipe-form">
        <div className="recipe-form__head">
          <label>
            Recipe name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Serves
            <input
              type="number"
              min="1"
              value={serves}
              onChange={(e) => setServes(e.target.value)}
              required
            />
          </label>
          <label>
            Source URL
            <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          </label>
        </div>

        <h2>Ingredients</h2>
        {lines.map((line) => (
          <LineRow
            key={line.key}
            line={line}
            onChange={(next) => updateLine(line.key, next)}
            onRemove={() => setLines((c) => c.filter((l) => l.key !== line.key))}
            onCreateRequest={(typedName) => setCreatingFor({ key: line.key, name: typedName })}
          />
        ))}
        <button type="button" onClick={() => setLines((c) => [...c, blankLine()])}>
          Add ingredient line
        </button>

        {creatingFor && (
          <div className="inline-create" role="form" aria-label="New ingredient">
            <h3>New ingredient</h3>
            <NewIngredientForm
              initialName={creatingFor.name}
              onCreated={ingredientCreated}
              onCancel={() => setCreatingFor(null)}
            />
          </div>
        )}

        <label className="block">
          Instructions
          <textarea
            rows={10}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>

        {error && <p className="error">{error}</p>}
        <div className="recipe-form__actions">
          <button className="primary" type="submit" disabled={save.isPending}>
            Save recipe
          </button>
          <button type="button" onClick={() => navigate('/recipes')}>
            Cancel
          </button>
        </div>
      </form>
    </section>
  )
}
```

The test finds the inline panel by `aria-label="New ingredient"`, which
`NewIngredientForm` already carries from Task 10.

- [ ] **Step 6: Build the recipe list page**

Create `frontend/src/pages/Recipes/RecipesPage.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteRecipe } from '../../api/client'
import { keys, useInvalidatingMutation, useRecipes } from '../../api/hooks'
import { useToast } from '../../components/Toast'

export function RecipesPage() {
  const [search, setSearch] = useState('')
  const { data: recipes = [], isLoading } = useRecipes(search || undefined)
  const toast = useToast()
  const remove = useInvalidatingMutation(deleteRecipe, [keys.recipes(), keys.recipes(search)])

  return (
    <section>
      <div className="page-head">
        <h1>Recipes</h1>
        <Link className="button primary" to="/recipes/new">
          New recipe
        </Link>
      </div>

      <input
        className="search"
        placeholder="Search recipes"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : recipes.length === 0 ? (
        <p className="muted">No recipes yet. Add one to start planning a week.</p>
      ) : (
        <ul className="cards">
          {recipes.map((recipe) => (
            <li key={recipe.id} className="card">
              <Link to={`/recipes/${recipe.id}`}>
                <strong>{recipe.name}</strong>
              </Link>
              <span className="muted">
                Serves {recipe.serves} · {recipe.line_count} ingredients
              </span>
              <button
                onClick={async () => {
                  try {
                    await remove.mutateAsync(recipe.id)
                  } catch (error) {
                    toast.showError(error)
                  }
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
```

- [ ] **Step 7: Append the styles**

Append to `frontend/src/styles.css`:

```css
.page-head { display: flex; align-items: center; justify-content: space-between; }
.button { display: inline-block; padding: 6px 12px; border-radius: 6px; text-decoration: none; border: 1px solid var(--border); }
.button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }

.cards { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.card { display: flex; flex-direction: column; gap: 6px; padding: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; align-items: flex-start; }

.recipe-form__head { display: flex; gap: 16px; flex-wrap: wrap; }
.recipe-form label { display: flex; flex-direction: column; gap: 4px; font-size: 0.9em; color: var(--muted); }
.recipe-form label.block { display: block; margin-top: 20px; }
.recipe-form textarea { width: 100%; font: inherit; }
.recipe-form__actions { display: flex; gap: 8px; margin-top: 20px; }

.line-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.line-row input[type='number'] { width: 90px; }

.picker { position: relative; }
.picker__chosen { display: inline-flex; gap: 8px; align-items: baseline; min-width: 180px; }
.picker__menu { position: absolute; z-index: 10; list-style: none; margin: 2px 0 0; padding: 4px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; min-width: 240px; box-shadow: 0 4px 12px rgb(0 0 0 / 0.08); }
.picker__menu button { display: block; width: 100%; text-align: left; border: none; background: none; padding: 6px 8px; }
.picker__menu button:hover { background: #eef3ef; }

.link { border: none; background: none; color: var(--accent); text-decoration: underline; padding: 0; cursor: pointer; font-size: 0.85em; }
.inline-create { margin: 16px 0; padding: 12px; border: 1px dashed var(--accent); border-radius: 8px; }
.inline-create h3 { margin-top: 0; }
.error { color: #b3261e; }
```

- [ ] **Step 8: Wire the routes**

In `frontend/src/App.tsx`, replace the `recipes`, `recipes/new`, and
`recipes/:recipeId` placeholders with `<RecipesPage />`, `<RecipeEditorPage />`,
and `<RecipeEditorPage />`.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `cd frontend && npm test`

Expected: PASS, all suites.

- [ ] **Step 10: Verify by hand**

Run `./dev.ps1` and at http://127.0.0.1:5173/recipes/new, enter a recipe with a
weighed ingredient in kg and a counted ingredient, save it, reopen it, and
confirm the kg amount reads back as kg rather than grams.

- [ ] **Step 11: Commit**

```bash
git add frontend/src
git commit -m "feat: add recipe list and unit-constrained recipe editor"
```

---

### Task 12: Planner

The 7 × 3 week grid. Its one piece of real logic is offering "leftovers of
Monday dinner" when you place a recipe that is already cooked earlier that
week, so that is what gets tested.

**Files:**
- Create: `frontend/src/pages/Planner/PlannerPage.tsx`
- Create: `frontend/src/pages/Planner/SlotPicker.tsx`
- Create: `frontend/src/pages/Planner/weeks.ts`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`
- Test: `frontend/src/pages/Planner/SlotPicker.test.tsx`

**Interfaces:**
- Consumes: `usePlan`, `usePlans`, `useRecipes`, `useInvalidatingMutation`, `keys`; `createPlan`, `addMeal`, `updateMeal`, `deleteMeal`, `generateList`; `SLOTS`, `DAY_NAMES`.
- Produces:
  - `weeks.ts`: `mondayOf(date: Date): string` returning `YYYY-MM-DD`, and `formatWeek(weekStart: string): string` returning e.g. `"Mon 17 Aug 2026"`
  - `SlotPicker({ day, slot, meals, recipes, onPick, onClose })` where `onPick: (choice: { recipeId: number; kind: MealKind; sourceMealId: number | null }) => void`
  - `leftoverOptions(recipeId: number, day: number, slot: MealSlot, meals: Meal[]): Meal[]` exported from `SlotPicker.tsx` — the cook meals of that recipe strictly earlier in the week
  - `PlannerPage`

`slotIndex(day, slot)` on the frontend mirrors the backend:
`day * 3 + SLOTS.indexOf(slot)`. Export it from `weeks.ts`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/pages/Planner/SlotPicker.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SlotPicker, leftoverOptions } from './SlotPicker'
import type { Meal, RecipeSummary } from '../../types'

const RECIPES: RecipeSummary[] = [
  { id: 10, name: 'Chili', serves: 4, line_count: 3 },
  { id: 11, name: 'Soup', serves: 2, line_count: 2 },
]

const MONDAY_CHILI: Meal = {
  id: 1,
  day: 0,
  slot: 'dinner',
  recipe_id: 10,
  recipe_name: 'Chili',
  recipe_serves: 4,
  kind: 'cook',
  servings_to_make: 4,
  servings_eaten: 2,
  source_meal_id: null,
}

describe('leftoverOptions', () => {
  it('offers an earlier cook of the same recipe', () => {
    expect(leftoverOptions(10, 1, 'lunch', [MONDAY_CHILI])).toEqual([MONDAY_CHILI])
  })

  it('offers nothing for a slot before the cook', () => {
    expect(leftoverOptions(10, 0, 'lunch', [MONDAY_CHILI])).toEqual([])
  })

  it('offers nothing for a different recipe', () => {
    expect(leftoverOptions(11, 1, 'lunch', [MONDAY_CHILI])).toEqual([])
  })

  it('never offers a leftovers meal as a source', () => {
    const leftover: Meal = {
      ...MONDAY_CHILI,
      id: 2,
      day: 1,
      slot: 'lunch',
      kind: 'leftovers',
      servings_to_make: null,
      source_meal_id: 1,
    }
    expect(leftoverOptions(10, 2, 'lunch', [MONDAY_CHILI, leftover])).toEqual([MONDAY_CHILI])
  })
})

describe('SlotPicker', () => {
  function renderPicker(day: number, meals: Meal[], onPick = vi.fn()) {
    render(
      <SlotPicker
        day={day}
        slot="lunch"
        meals={meals}
        recipes={RECIPES}
        onPick={onPick}
        onClose={vi.fn()}
      />,
    )
    return onPick
  }

  it('lists leftovers first when the recipe is already cooked earlier', async () => {
    const user = userEvent.setup()
    renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')

    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options[0]).toMatch(/leftovers of mon dinner/i)
    expect(options[1]).toMatch(/cook chili/i)
  })

  it('reports a leftovers choice with its source meal', async () => {
    const user = userEvent.setup()
    const onPick = renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')
    await user.click(screen.getByRole('option', { name: /leftovers of mon dinner/i }))

    expect(onPick).toHaveBeenCalledWith({ recipeId: 10, kind: 'leftovers', sourceMealId: 1 })
  })

  it('reports a cook choice with no source', async () => {
    const user = userEvent.setup()
    const onPick = renderPicker(1, [MONDAY_CHILI])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'soup')
    await user.click(screen.getByRole('option', { name: /cook soup/i }))

    expect(onPick).toHaveBeenCalledWith({ recipeId: 11, kind: 'cook', sourceMealId: null })
  })

  it('offers only cooking when nothing is planned yet', async () => {
    const user = userEvent.setup()
    renderPicker(1, [])
    await user.type(screen.getByPlaceholderText(/search recipes/i), 'chili')

    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Cook Chili (serves 4)'])
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test`

Expected: FAIL — `Failed to resolve import "./SlotPicker"`.

- [ ] **Step 3: Write the week helpers**

Create `frontend/src/pages/Planner/weeks.ts`:

```ts
import { DAY_NAMES, SLOTS } from '../../types'
import type { MealSlot } from '../../types'

/** The Monday of the week containing `date`, as YYYY-MM-DD. */
export function mondayOf(date: Date): string {
  const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const offset = (copy.getDay() + 6) % 7 // Sunday is 0, so shift to Monday-first
  copy.setDate(copy.getDate() - offset)
  const month = String(copy.getMonth() + 1).padStart(2, '0')
  const day = String(copy.getDate()).padStart(2, '0')
  return `${copy.getFullYear()}-${month}-${day}`
}

export function formatWeek(weekStart: string): string {
  const [year, month, day] = weekStart.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** A single comparable position in the week, mirroring the backend. */
export function slotIndex(day: number, slot: MealSlot): number {
  return day * SLOTS.length + SLOTS.indexOf(slot)
}

export function slotLabel(day: number, slot: MealSlot): string {
  return `${DAY_NAMES[day]} ${slot}`
}
```

- [ ] **Step 4: Build the slot picker**

Create `frontend/src/pages/Planner/SlotPicker.tsx`:

```tsx
import { useState } from 'react'
import type { Meal, MealKind, MealSlot, RecipeSummary } from '../../types'
import { slotIndex, slotLabel } from './weeks'

/** Cook meals of this recipe that happen strictly earlier in the week. */
export function leftoverOptions(
  recipeId: number,
  day: number,
  slot: MealSlot,
  meals: Meal[],
): Meal[] {
  const here = slotIndex(day, slot)
  return meals.filter(
    (meal) =>
      meal.kind === 'cook' &&
      meal.recipe_id === recipeId &&
      slotIndex(meal.day, meal.slot) < here,
  )
}

interface Props {
  day: number
  slot: MealSlot
  meals: Meal[]
  recipes: RecipeSummary[]
  onPick: (choice: { recipeId: number; kind: MealKind; sourceMealId: number | null }) => void
  onClose: () => void
}

export function SlotPicker({ day, slot, meals, recipes, onPick, onClose }: Props) {
  const [query, setQuery] = useState('')
  const trimmed = query.trim().toLowerCase()
  const matches = trimmed
    ? recipes.filter((recipe) => recipe.name.toLowerCase().includes(trimmed))
    : []

  return (
    <div className="slot-picker">
      <input
        autoFocus
        placeholder="Search recipes"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      />
      <ul role="listbox">
        {matches.flatMap((recipe) => {
          // Leftovers come first: if the recipe is already cooked this week,
          // reusing that batch is almost always what you meant.
          const sources = leftoverOptions(recipe.id, day, slot, meals)
          return [
            ...sources.map((source) => (
              <li key={`leftover-${recipe.id}-${source.id}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() =>
                    onPick({ recipeId: recipe.id, kind: 'leftovers', sourceMealId: source.id })
                  }
                >
                  Leftovers of {slotLabel(source.day, source.slot)} ({recipe.name})
                </button>
              </li>
            )),
            <li key={`cook-${recipe.id}`}>
              <button
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => onPick({ recipeId: recipe.id, kind: 'cook', sourceMealId: null })}
              >
                Cook {recipe.name} (serves {recipe.serves})
              </button>
            </li>,
          ]
        })}
      </ul>
    </div>
  )
}
```

- [ ] **Step 5: Build the planner page**

Create `frontend/src/pages/Planner/PlannerPage.tsx`:

```tsx
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { addMeal, createPlan, deleteMeal, generateList, updateMeal } from '../../api/client'
import { keys, useInvalidatingMutation, usePlan, usePlans, useRecipes } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { DAY_NAMES, SLOTS } from '../../types'
import type { Meal, MealSlot } from '../../types'
import { SlotPicker } from './SlotPicker'
import { formatWeek, mondayOf } from './weeks'

export function PlannerPage() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const { data: plans = [] } = usePlans()
  const id = planId ? Number(planId) : plans[0]?.id
  const { data: plan } = usePlan(id)
  const { data: recipes = [] } = useRecipes()
  const [openSlot, setOpenSlot] = useState<{ day: number; slot: MealSlot } | null>(null)

  const invalidate = [keys.plans(), ...(id ? [keys.plan(id), keys.list(id)] : [])]
  const newPlan = useInvalidatingMutation(createPlan, [keys.plans()])
  const placeMeal = useInvalidatingMutation(
    (args: { planId: number; body: Parameters<typeof addMeal>[1] }) =>
      addMeal(args.planId, args.body),
    invalidate,
  )
  const editMeal = useInvalidatingMutation(
    (args: { mealId: number; body: Parameters<typeof updateMeal>[1] }) =>
      updateMeal(args.mealId, args.body),
    invalidate,
  )
  const removeMeal = useInvalidatingMutation(deleteMeal, invalidate)
  const makeList = useInvalidatingMutation(generateList, invalidate)

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (error) {
      toast.showError(error)
    }
  }

  if (!plan) {
    return (
      <section>
        <h1>Planner</h1>
        <p className="muted">No week planned yet.</p>
        <button
          className="primary"
          onClick={() =>
            run(
              newPlan
                .mutateAsync(mondayOf(new Date()))
                .then((created) => navigate(`/planner/${created.id}`)),
            )
          }
        >
          Start this week
        </button>
      </section>
    )
  }

  const mealAt = (day: number, slot: MealSlot): Meal | undefined =>
    plan.meals.find((meal) => meal.day === day && meal.slot === slot)
  const warningFor = (mealId: number) => plan.warnings.find((w) => w.meal_id === mealId)

  return (
    <section>
      <div className="page-head">
        <h1>Week of {formatWeek(plan.week_start)}</h1>
        <div className="page-head__actions">
          <select
            value={plan.id}
            onChange={(e) => navigate(`/planner/${e.target.value}`)}
            aria-label="Choose a week"
          >
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {formatWeek(p.week_start)}
              </option>
            ))}
          </select>
          <button
            onClick={() =>
              run(
                newPlan
                  .mutateAsync(mondayOf(new Date(Date.now() + 7 * 86400000)))
                  .then((created) => navigate(`/planner/${created.id}`)),
              )
            }
          >
            New week
          </button>
          <button
            className="primary"
            onClick={() => run(makeList.mutateAsync(plan.id).then(() => navigate(`/list/${plan.id}`)))}
          >
            Generate shopping list
          </button>
        </div>
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th />
            {DAY_NAMES.map((day) => (
              <th key={day}>{day}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {SLOTS.map((slot) => (
            <tr key={slot}>
              <th scope="row">{slot}</th>
              {DAY_NAMES.map((_, day) => {
                const meal = mealAt(day, slot)
                const isOpen = openSlot?.day === day && openSlot.slot === slot
                return (
                  <td key={day} className="grid__cell">
                    {meal ? (
                      <div className={`meal meal--${meal.kind}`}>
                        <strong>{meal.recipe_name}</strong>
                        {meal.kind === 'cook' ? (
                          <label className="meal__servings">
                            makes
                            <input
                              type="number"
                              min="1"
                              value={meal.servings_to_make ?? 1}
                              aria-label={`Servings for ${meal.recipe_name} on ${DAY_NAMES[day]} ${slot}`}
                              onChange={(e) =>
                                run(
                                  editMeal.mutateAsync({
                                    mealId: meal.id,
                                    body: { servings_to_make: Number(e.target.value) },
                                  }),
                                )
                              }
                            />
                          </label>
                        ) : (
                          <span className="muted">leftovers</span>
                        )}
                        {warningFor(meal.id) && (
                          <span className="badge--warn" title={warningFor(meal.id)!.message}>
                            ⚠ short
                          </span>
                        )}
                        <button
                          className="link"
                          onClick={() => run(removeMeal.mutateAsync(meal.id))}
                        >
                          remove
                        </button>
                      </div>
                    ) : isOpen ? (
                      <SlotPicker
                        day={day}
                        slot={slot}
                        meals={plan.meals}
                        recipes={recipes}
                        onClose={() => setOpenSlot(null)}
                        onPick={(choice) => {
                          setOpenSlot(null)
                          run(
                            placeMeal.mutateAsync({
                              planId: plan.id,
                              body: {
                                day,
                                slot,
                                recipe_id: choice.recipeId,
                                kind: choice.kind,
                                source_meal_id: choice.sourceMealId,
                              },
                            }),
                          )
                        }}
                      />
                    ) : (
                      <button className="grid__add" onClick={() => setOpenSlot({ day, slot })}>
                        +
                      </button>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {plan.warnings.length > 0 && (
        <ul className="warnings">
          {plan.warnings.map((warning) => (
            <li key={warning.meal_id} className="badge--warn">
              {warning.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
```

- [ ] **Step 6: Append the styles**

Append to `frontend/src/styles.css`:

```css
.page-head__actions { display: flex; gap: 8px; align-items: center; }

.grid { table-layout: fixed; }
.grid th { text-transform: capitalize; }
.grid__cell { vertical-align: top; height: 92px; position: relative; }
.grid__add { width: 100%; border-style: dashed; color: var(--muted); }

.meal { display: flex; flex-direction: column; gap: 4px; font-size: 0.9em; }
.meal--leftovers { opacity: 0.75; }
.meal__servings { display: flex; gap: 4px; align-items: center; color: var(--muted); }
.meal__servings input { width: 54px; }

.slot-picker { position: absolute; z-index: 20; background: var(--surface); border: 1px solid var(--accent); border-radius: 6px; padding: 6px; width: 260px; box-shadow: 0 4px 12px rgb(0 0 0 / 0.12); }
.slot-picker ul { list-style: none; margin: 4px 0 0; padding: 0; max-height: 200px; overflow-y: auto; }
.slot-picker button { display: block; width: 100%; text-align: left; border: none; background: none; padding: 6px; font-size: 0.9em; }
.slot-picker button:hover { background: #eef3ef; }

.warnings { list-style: none; padding: 0; margin-top: 16px; }
```

- [ ] **Step 7: Wire the routes**

In `frontend/src/App.tsx`, replace both `planner` placeholders with
`<PlannerPage />`.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd frontend && npm test`

Expected: PASS, all suites.

- [ ] **Step 9: Verify by hand**

Run `./dev.ps1`, start a week, place a recipe in Monday dinner, then click
Tuesday lunch and search the same recipe — confirm "Leftovers of Mon dinner"
is the first option. Add two leftover slots for a 4-serving batch and confirm
the amber "short" badge appears; raise the batch to 6 and confirm it clears.

- [ ] **Step 10: Commit**

```bash
git add frontend/src
git commit -m "feat: add week planner with leftover slots and batch warnings"
```

---

### Task 13: Shopping list page

**Files:**
- Create: `frontend/src/pages/ShoppingList/ShoppingListPage.tsx`
- Create: `frontend/src/pages/ShoppingList/ManualAdd.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `useList`, `useSuggestions`, `useInvalidatingMutation`, `keys`; `addListItem`, `updateListItem`, `deleteListItem`, `finalizeList`, `generateList`; `CATEGORY_ORDER`, `CATEGORY_LABELS`.
- Produces:
  - `groupByCategory(items: ListItem[]): { category: Category | null; label: string; items: ListItem[] }[]` exported from `ShoppingListPage.tsx`
  - `ManualAdd({ listId, planId }: { listId: number; planId: number })` — `planId` is needed to invalidate the right list query key
  - `ShoppingListPage`

The backend already returns items in store-walk order, so `groupByCategory`
only has to chunk consecutive runs — it must not re-sort.

- [ ] **Step 1: Build the manual-add control**

Create `frontend/src/pages/ShoppingList/ManualAdd.tsx`:

```tsx
import { useState } from 'react'
import { addListItem } from '../../api/client'
import { keys, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'

export function ManualAdd({ listId, planId }: { listId: number; planId: number }) {
  const [name, setName] = useState('')
  const toast = useToast()
  const add = useInvalidatingMutation(
    (customName: string) => addListItem(listId, { custom_name: customName }),
    [keys.list(planId), keys.suggestions(listId)],
  )

  return (
    <form
      className="manual-add"
      onSubmit={async (event) => {
        event.preventDefault()
        if (!name.trim()) return
        try {
          await add.mutateAsync(name.trim())
          setName('')
        } catch (error) {
          toast.showError(error)
        }
      }}
    >
      <input
        placeholder="Add something not from a recipe"
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label="Add an item"
      />
      <button type="submit">Add</button>
    </form>
  )
}
```

- [ ] **Step 2: Build the page**

Create `frontend/src/pages/ShoppingList/ShoppingListPage.tsx`:

```tsx
import { useParams } from 'react-router-dom'
import {
  addListItem,
  deleteListItem,
  finalizeList,
  generateList,
  updateListItem,
} from '../../api/client'
import { keys, useInvalidatingMutation, useList, useSuggestions } from '../../api/hooks'
import { useToast } from '../../components/Toast'
import { CATEGORY_LABELS } from '../../types'
import type { Category, ListItem } from '../../types'
import { formatWeek } from '../Planner/weeks'
import { ManualAdd } from './ManualAdd'

/** Chunk consecutive runs of the same category. The API already ordered them. */
export function groupByCategory(
  items: ListItem[],
): { category: Category | null; label: string; items: ListItem[] }[] {
  const groups: { category: Category | null; label: string; items: ListItem[] }[] = []
  for (const item of items) {
    const last = groups[groups.length - 1]
    if (last && last.category === item.category) {
      last.items.push(item)
    } else {
      groups.push({
        category: item.category,
        label: item.category ? CATEGORY_LABELS[item.category] : 'Other items',
        items: [item],
      })
    }
  }
  return groups
}

function amountOf(item: ListItem): string {
  if (item.display_quantity == null) return ''
  if (item.display_unit === 'count') return `${item.display_quantity} ×`
  return `${item.display_quantity} ${item.display_unit}`
}

function why(item: ListItem): string | undefined {
  if (item.contributions.length === 0) return undefined
  return item.contributions
    .map((c) => `${c.recipe_name}: ${Math.round(c.quantity * 100) / 100}`)
    .join('\n')
}

export function ShoppingListPage() {
  const planId = Number(useParams().planId)
  const { data: list, isLoading, error } = useList(planId)
  const { data: suggestions = [] } = useSuggestions(list?.id)
  const toast = useToast()

  const invalidate = [keys.list(planId), keys.plans(), keys.history()]
  const check = useInvalidatingMutation(
    (args: { itemId: number; checked: boolean }) =>
      updateListItem(list!.id, args.itemId, { checked: args.checked }),
    invalidate,
  )
  const drop = useInvalidatingMutation(
    (itemId: number) => deleteListItem(list!.id, itemId),
    invalidate,
  )
  const accept = useInvalidatingMutation(
    (args: { ingredientId: number | null; name: string }) =>
      addListItem(list!.id, {
        ingredient_id: args.ingredientId,
        custom_name: args.ingredientId ? null : args.name,
      }),
    [...invalidate, ...(list ? [keys.suggestions(list.id)] : [])],
  )
  const regenerate = useInvalidatingMutation(() => generateList(planId), invalidate)
  const finish = useInvalidatingMutation(() => finalizeList(list!.id), invalidate)

  async function run(action: Promise<unknown>) {
    try {
      await action
    } catch (err) {
      toast.showError(err)
    }
  }

  if (isLoading) return <p className="muted">Loading…</p>
  if (error || !list) {
    return (
      <section>
        <h1>Shopping list</h1>
        <p className="muted">
          No list for this week yet. Generate one from the planner.
        </p>
      </section>
    )
  }

  const buy = list.items.filter((item) => item.section === 'buy')
  const staples = list.items.filter((item) => item.section === 'staple_check')

  return (
    <section className="shopping">
      <div className="page-head no-print">
        <h1>Shopping list — {formatWeek(list.week_start)}</h1>
        <div className="page-head__actions">
          <button onClick={() => run(regenerate.mutateAsync())}>Regenerate</button>
          <button onClick={() => window.print()}>Print</button>
          <button
            className="primary"
            disabled={list.finalized_at != null}
            onClick={() => run(finish.mutateAsync())}
          >
            {list.finalized_at ? 'Shopping done' : 'Done shopping'}
          </button>
        </div>
      </div>

      <h1 className="print-only">Shopping list — {formatWeek(list.week_start)}</h1>

      {groupByCategory(buy).map((group) => (
        <div key={group.label} className="aisle">
          <h2>{group.label}</h2>
          <ul className="items">
            {group.items.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <label>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={(e) =>
                      run(check.mutateAsync({ itemId: item.id, checked: e.target.checked }))
                    }
                  />
                  <span className="item__amount">{amountOf(item)}</span>
                  <span className="item__name" title={why(item)}>
                    {item.name}
                  </span>
                  {item.source !== 'recipe' && <span className="muted no-print"> (added)</span>}
                </label>
                {item.source !== 'recipe' && (
                  <button className="link no-print" onClick={() => run(drop.mutateAsync(item.id))}>
                    remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {buy.length === 0 && <p className="muted">Nothing to buy yet.</p>}

      {staples.length > 0 && (
        <div className="aisle">
          <h2>Check your seasonings</h2>
          <ul className="items">
            {staples.map((item) => (
              <li key={item.id} className="item">
                <label>
                  <input
                    type="checkbox"
                    checked={item.checked}
                    onChange={(e) =>
                      run(check.mutateAsync({ itemId: item.id, checked: e.target.checked }))
                    }
                  />
                  <span className="item__name">{item.name}</span>
                  <span className="muted">
                    {' '}
                    — {item.contributions.map((c) => c.recipe_name).join(', ')}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="no-print">
        <ManualAdd listId={list.id} planId={planId} />
        {suggestions.length > 0 && (
          <div className="suggestions">
            <span className="muted">You usually buy:</span>
            {suggestions.map((suggestion) => (
              <button
                key={`${suggestion.ingredient_id ?? suggestion.name}`}
                onClick={() =>
                  run(
                    accept.mutateAsync({
                      ingredientId: suggestion.ingredient_id,
                      name: suggestion.name,
                    }),
                  )
                }
              >
                + {suggestion.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Append the styles**

Append to `frontend/src/styles.css`:

```css
.aisle { margin-bottom: 20px; }
.aisle h2 { font-size: 1em; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.items { list-style: none; padding: 0; margin: 8px 0 0; }
.item { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }
.item label { display: flex; align-items: baseline; gap: 8px; cursor: pointer; }
.item--checked .item__name { text-decoration: line-through; color: var(--muted); }
.item__amount { min-width: 72px; color: var(--muted); font-variant-numeric: tabular-nums; }

.manual-add { display: flex; gap: 8px; margin-top: 24px; }
.manual-add input { width: 320px; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 12px; }
.print-only { display: none; }
```

- [ ] **Step 4: Wire the route**

In `frontend/src/App.tsx`, replace the `list/:planId` placeholder with
`<ShoppingListPage />`.

- [ ] **Step 5: Verify by hand**

Run `./dev.ps1`. From a planned week, generate a list and confirm: items are
grouped by aisle; hovering a name shows which recipes wanted it; seasonings
appear only under "Check your seasonings"; a manual item can be added and
removed. Then change a meal's servings in the planner, hit Regenerate, and
confirm the quantity updates while a checked box and a manual item both
survive.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: add shopping list page with aisle grouping and suggestions"
```

---

### Task 14: Print stylesheet

**Files:**
- Modify: `frontend/src/print.css`

**Interfaces:**
- Consumes: the class names `no-print`, `print-only`, `aisle`, `items`, `item`, `item__amount`, `nav`, `layout` from Tasks 9 and 13.
- Produces: no new exports.

- [ ] **Step 1: Write the stylesheet**

Replace `frontend/src/print.css`:

```css
@media print {
  @page {
    margin: 14mm;
  }

  body {
    background: #fff;
  }

  /* Chrome and hover affordances have no meaning on paper. */
  .nav,
  .no-print,
  button {
    display: none !important;
  }

  .print-only {
    display: block !important;
  }

  .layout {
    max-width: none;
    padding: 0;
  }

  .content {
    padding-top: 0;
  }

  .shopping h1 {
    font-size: 16pt;
    margin: 0 0 10pt;
  }

  .aisle {
    /* Keep an aisle's heading with at least some of its items. */
    break-inside: avoid;
    margin-bottom: 10pt;
  }

  .aisle h2 {
    font-size: 10pt;
    color: #000;
    border-bottom: 1px solid #000;
  }

  .item {
    font-size: 12pt;
    padding: 3pt 0;
    break-inside: avoid;
  }

  .item__amount {
    min-width: 70pt;
  }

  /* Real checkboxes print faintly; draw hollow squares instead. */
  .item input[type='checkbox'] {
    appearance: none;
    width: 12pt;
    height: 12pt;
    border: 1pt solid #000;
    margin-right: 6pt;
  }

  /* A checked item is still worth printing, just not struck through. */
  .item--checked .item__name {
    text-decoration: none;
    color: #000;
  }

  .muted {
    color: #444;
  }
}
```

- [ ] **Step 2: Verify by hand**

With a generated list open, press Ctrl+P. Confirm the preview shows one clean
page: no nav, no buttons, the week in the heading, aisle headings with hollow
checkboxes, and text large enough to read at arm's length.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/print.css
git commit -m "feat: add print stylesheet for the shopping list"
```

---

### Task 15: History, household size, and end-to-end verification

The last screens plus a full manual pass over the success criteria.

**Files:**
- Create: `frontend/src/pages/History/HistoryPage.tsx`
- Create: `frontend/src/pages/History/ArchivedListPage.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/components/Layout.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `useListHistory`, `useListById`, `useSettings`, `useInvalidatingMutation`, `keys`; `updateSettings`; `groupByCategory` from Task 13; `formatWeek` from Task 12.
- Produces: `HistoryPage`, `ArchivedListPage`, and a household-size control in `Layout`.

- [ ] **Step 1: Build the history pages**

Create `frontend/src/pages/History/HistoryPage.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { useListHistory } from '../../api/hooks'
import { formatWeek } from '../Planner/weeks'

export function HistoryPage() {
  const { data: history = [], isLoading } = useListHistory()

  if (isLoading) return <p className="muted">Loading…</p>

  return (
    <section>
      <h1>Past weeks</h1>
      {history.length === 0 ? (
        <p className="muted">
          Nothing here yet. A week lands here once you mark its list "Done shopping".
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Week</th>
              <th>Bought</th>
              <th>Skipped</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {history.map((entry) => (
              <tr key={entry.id}>
                <td>{formatWeek(entry.week_start)}</td>
                <td>{entry.checked_count}</td>
                <td>{entry.item_count - entry.checked_count}</td>
                <td>
                  <Link to={`/history/${entry.id}`}>View list</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
```

Create `frontend/src/pages/History/ArchivedListPage.tsx`:

```tsx
import { Link, useParams } from 'react-router-dom'
import { useListById } from '../../api/hooks'
import { groupByCategory } from '../ShoppingList/ShoppingListPage'
import { formatWeek } from '../Planner/weeks'

export function ArchivedListPage() {
  const listId = Number(useParams().listId)
  const { data: list, isLoading } = useListById(listId)

  if (isLoading) return <p className="muted">Loading…</p>
  if (!list) return <p className="muted">No such list.</p>

  const buy = list.items.filter((item) => item.section === 'buy')

  return (
    <section className="shopping">
      <div className="page-head no-print">
        <h1>{formatWeek(list.week_start)}</h1>
        <Link to="/history">Back to history</Link>
      </div>

      {groupByCategory(buy).map((group) => (
        <div key={group.label} className="aisle">
          <h2>{group.label}</h2>
          <ul className="items">
            {group.items.map((item) => (
              <li key={item.id} className={item.checked ? 'item item--checked' : 'item'}>
                <span className="item__amount">
                  {item.display_quantity != null
                    ? item.display_unit === 'count'
                      ? `${item.display_quantity} ×`
                      : `${item.display_quantity} ${item.display_unit}`
                    : ''}
                </span>
                <span className="item__name">{item.name}</span>
                <span className="muted">{item.checked ? 'bought' : 'skipped'}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
```

- [ ] **Step 2: Add the household-size control**

In `frontend/src/components/Layout.tsx`, add a small control to the right of
the nav links:

```tsx
import { NavLink, Outlet } from 'react-router-dom'
import { updateSettings } from '../api/client'
import { keys, useInvalidatingMutation, useSettings } from '../api/hooks'

const LINKS = [
  { to: '/planner', label: 'Planner' },
  { to: '/recipes', label: 'Recipes' },
  { to: '/ingredients', label: 'Ingredients' },
  { to: '/history', label: 'History' },
]

export function Layout() {
  const { data: settings } = useSettings()
  const save = useInvalidatingMutation(updateSettings, [keys.settings()])

  return (
    <div className="layout">
      <nav className="nav">
        <span className="nav__brand">RatKitchen</span>
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => (isActive ? 'nav__link nav__link--active' : 'nav__link')}
          >
            {link.label}
          </NavLink>
        ))}
        <label className="nav__setting">
          Household
          <input
            type="number"
            min="1"
            value={settings?.household_size ?? 2}
            onChange={(e) => save.mutate(Number(e.target.value))}
          />
        </label>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
```

Append to `frontend/src/styles.css`:

```css
.nav__setting { margin-left: auto; display: flex; gap: 6px; align-items: center; color: var(--muted); font-size: 0.9em; }
.nav__setting input { width: 56px; }
```

- [ ] **Step 3: Wire the routes**

In `frontend/src/App.tsx`, replace the `history` and `history/:listId`
placeholders with `<HistoryPage />` and `<ArchivedListPage />`. Delete the now
unused `Placeholder` component.

- [ ] **Step 4: Run the full test suite**

```bash
cd backend && .venv/Scripts/python -m pytest -v
cd ../frontend && npm test
```

Expected: PASS on both. Record the actual counts; do not claim success without
seeing them.

- [ ] **Step 5: Walk the success criteria end to end**

Run `./dev.ps1` and confirm each of these, in order:

1. Enter a recipe with at least one weighed and one counted ingredient,
   creating a new ingredient inline without leaving the page.
2. Plan a week including a cook slot and a leftovers slot of the same recipe.
3. Generate the list. Confirm the leftovers slot added nothing, quantities
   summed across recipes, and nothing rounded down.
4. Tick two items, add "Paper towels" manually, then change a meal's servings
   and hit Regenerate. Confirm the ticks and the manual item both survived and
   the quantity changed.
5. Print-preview the list and confirm it is legible and fits cleanly.
6. Mark it done, confirm it appears under History, and confirm the plan's
   status reads `done`.
7. Repeat weeks 2 and 3 with "Paper towels" added manually each time, then on
   week 4 confirm it appears as a suggestion chip and is not auto-added.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: add list history, archived list view, and household size"
```

---

## Spec Coverage

| Spec requirement | Task |
|---|---|
| Ingredient table, category-to-unit defaults | 2, 4 |
| Unit families and exact conversion | 1 |
| Recipe and RecipeIngredient | 2, 5 |
| MealPlan and PlannedMeal, slot uniqueness, leftover constraints | 2, 6 |
| Batch-coverage warning | 6, 12 |
| ShoppingList and ShoppingListItem | 2, 7 |
| Setting / household_size | 2, 4, 15 |
| `generate_list` scaling, summing, round-up, display units, aisle order | 3 |
| Staple partitioning | 3, 7, 13 |
| Regeneration preservation rules | 7 |
| Repeat-buy suggestions (3 of 4) | 8 |
| Every API route and error code | 4–8 |
| Recipe editor with inline ingredient creation | 11 |
| Ingredients catalog page | 10 |
| Planner grid with leftovers | 12 |
| Shopping list page, contributions, manual add, suggestion chips | 13 |
| Print stylesheet | 14 |
| History | 15 |
| Success criteria 1–6 | 15, Step 5 |
