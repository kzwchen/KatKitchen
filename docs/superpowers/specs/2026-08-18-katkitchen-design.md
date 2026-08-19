# KatKitchen — Design Spec

**Date:** 2026-08-18
**Status:** Approved for planning

## Purpose

A local, single-user web app for planning a week of meals and producing one
accurate shopping list for one weekly trip. It answers a single question well:
*given what I plan to cook this week, exactly what do I need to buy?*

## Scope

**In scope:** recipe storage with structured ingredient amounts; an ingredient
catalog with fixed units; a day-by-day weekly meal plan with leftover tracking;
shopping list generation, editing, and printing; archived past lists;
repeat-buy suggestions.

**Out of scope:** live pantry inventory, recipe import from URLs, nutrition
data, multi-user support, authentication, mobile-optimized layouts, hosting
beyond localhost.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Inventory tracking | Checklist only | A depleting pantry requires logging every meal actually cooked; the numbers drift and stop being trusted. |
| Access | Desktop web app on localhost, printed list | No phone use in-store, so no responsive work, no network exposure, no auth. |
| Planning granularity | 7 days × breakfast/lunch/dinner | User wants to see what they are eating on a given day. |
| Unit handling | Unit is fixed per **ingredient**, not per recipe line | Makes the "2 onions + 150 g onion" conflict unrepresentable. Aggregation becomes plain addition with no density tables. |
| Seasonings | Amounts stored in recipes, excluded from list quantities | Summing teaspoons doesn't tell you whether to buy a jar. A "check your rack" reminder does. |
| Leftovers | Explicit `leftovers` slot kind contributing zero ingredients | Lets the plan show Tuesday's lunch without double-buying. |
| Rounding | Always up | A list that rounds down leaves you short mid-recipe. |
| Stack | React + TypeScript + Vite frontend; FastAPI + SQLModel + SQLite backend | User's stated preference. |

## Data Model

SQLite via SQLModel. Database at `data/katkitchen.db`.

### Ingredient

The catalog. One row per distinct thing you buy.

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | str, unique | Case-insensitive uniqueness. |
| `category` | enum | `produce`, `meat_seafood`, `dairy`, `dry_goods`, `frozen`, `bakery`, `seasoning`, `other` |
| `unit` | enum | `count`, `g`, `ml`. Chosen at creation, defaulted from category, editable only while unused by any recipe. |
| `is_staple` | bool | Defaults true for `seasoning`, false otherwise. Staples are excluded from quantity aggregation. |

Category-to-unit defaults: produce → `count`; meat_seafood → `g`;
dry_goods → `g`; bakery → `count`; dairy → `ml`; frozen → `g`;
seasoning → `ml`; other → `count`. The default is a suggestion; the user may
override it at creation (e.g. spinach bought by weight → `g`).

### Unit families and conversion

Quantities are always **stored** in the ingredient's canonical unit. The user
may **enter** any unit in the same family; conversion is exact and requires no
per-ingredient data.

| Family | Canonical | Accepted entry units |
|---|---|---|
| count | `count` | count |
| mass | `g` | g, kg, oz, lb |
| volume | `ml` | ml, l, tsp, tbsp, cup |

Cross-family conversion is never attempted. Because units are fixed per
ingredient, cross-family aggregation cannot arise.

### Recipe

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | str | |
| `serves` | int | Base yield. Scaling divisor. |
| `instructions` | text | Plain text / markdown. |
| `source_url` | str, nullable | Reference only; nothing is fetched. |
| `notes` | text, nullable | |
| `created_at`, `updated_at` | datetime | |

### RecipeIngredient

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `recipe_id` | FK | |
| `ingredient_id` | FK | |
| `quantity` | float | Stored in the ingredient's canonical unit. |
| `display_unit` | str | What the user typed, so the recipe page reads naturally. |
| `prep_note` | str, nullable | "diced", "boneless". |
| `position` | int | Display order. |

### MealPlan

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `week_start` | date, unique | Monday of the week. |
| `status` | enum | `planning`, `shopping`, `done` |
| `created_at` | datetime | |

### PlannedMeal

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `plan_id` | FK | |
| `day` | int 0–6 | 0 = Monday. |
| `slot` | enum | `breakfast`, `lunch`, `dinner` |
| `recipe_id` | FK | |
| `kind` | enum | `cook` or `leftovers` |
| `servings_to_make` | int, nullable | Cook slots only. Defaults to `recipe.serves`. |
| `servings_eaten` | int | Defaults to the `household_size` setting. |
| `source_meal_id` | FK, nullable | Leftover slots only; points at the cook slot. |

Constraints:

- `(plan_id, day, slot)` is unique — one meal per slot.
- A `leftovers` meal must have a `source_meal_id` referencing a `cook` meal in
  the same plan, for the same recipe, at an earlier `(day, slot)` position.
- A `cook` meal must have `source_meal_id` null and `servings_to_make` set.

Validation (warning, not rejection): for each cook meal, if the sum of
`servings_eaten` across that meal and all meals referencing it exceeds
`servings_to_make`, the planner shows an amber badge on the slot.

### ShoppingList

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `plan_id` | FK, unique | One list per plan. |
| `generated_at` | datetime | Updated on each regeneration. |
| `finalized_at` | datetime, nullable | Set by "Done shopping". |

### ShoppingListItem

| Field | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `list_id` | FK | |
| `ingredient_id` | FK, nullable | Null for free-text items. |
| `custom_name` | str, nullable | Set only when `ingredient_id` is null. |
| `quantity` | float, nullable | Canonical unit. Null for staple-check and free-text items. |
| `display_unit` | str, nullable | Friendliest unit for display. |
| `source` | enum | `recipe`, `manual`, `suggested` |
| `section` | enum | `buy` or `staple_check` |
| `checked` | bool | |
| `note` | str, nullable | |
| `contributions` | JSON | `[{recipe_id, recipe_name, quantity}]` — why this line exists. |

Exactly one of `ingredient_id` / `custom_name` is set.

### Setting

A single-row table of typed columns. Currently holds `household_size`
(default 2).

## Shopping List Generation

`generate_list(plan, recipes, ingredients) -> ListDraft` is a pure function.
No database access, no I/O. This is the core testable unit.

1. Select `cook` meals only. Leftover meals contribute nothing.
2. For each cook meal, `scale = servings_to_make / recipe.serves`.
3. For each of that recipe's ingredients, `scaled = quantity * scale`, and
   record a contribution `{recipe_id, recipe_name, scaled}`.
4. Group by `ingredient_id` and sum. Units match by construction.
5. Partition: ingredients with `is_staple = true` go to the `staple_check`
   section with quantity null, carrying only their contribution list.
   Everything else goes to `buy`.
6. Round up. `count` rounds up to the next whole number. `g` and `ml` round up
   to the next multiple of 10. Rounding is applied after summing, once per
   ingredient.
7. Choose a display unit: `g` ≥ 1000 renders as kg; `ml` ≥ 1000 renders as l;
   otherwise canonical.
8. Order by category in store-walk order: produce, bakery, meat_seafood,
   dairy, frozen, dry_goods, other. Within a category, alphabetical.

### Regeneration

Regenerating an existing list must not discard user work.

- Recipe-derived `buy` and `staple_check` items are recomputed from scratch.
- Items with `source` of `manual` or `suggested` are preserved untouched.
- `checked` state is preserved for any recomputed item whose `ingredient_id`
  matches a pre-existing item, **including** when its quantity changed.
- An item that no longer has any contributing recipe is removed, even if it was
  checked, unless its `source` is `manual` or `suggested`.
- `note` text on a recomputed item is preserved by `ingredient_id`.

### Repeat-buy suggestions

`GET /suggestions` returns items whose `source` is `manual` and which appear in
at least 3 of the 4 most recently finalized lists, matched by `ingredient_id`
or normalized `custom_name`. Items already present on the current list are
excluded. Suggestions are offered as chips in the UI and are **never** added
automatically.

## API

All routes prefixed `/api`. Server binds to `127.0.0.1`.

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/ingredients` | List (with search), create |
| GET/PATCH/DELETE | `/ingredients/{id}` | Read, update, delete |
| GET/POST | `/recipes` | List (with search), create with nested ingredients |
| GET/PATCH/DELETE | `/recipes/{id}` | Read, update (nested replace), delete |
| GET/POST | `/plans` | List, create for a week |
| GET/DELETE | `/plans/{id}` | Read with meals, delete |
| POST | `/plans/{id}/meals` | Add a meal to a slot |
| PATCH/DELETE | `/meals/{id}` | Edit servings/kind, remove |
| GET | `/plans/{id}/list` | Fetch the list; 404 if not yet generated |
| POST | `/plans/{id}/list` | Generate, or regenerate preserving per the rules above |
| POST | `/lists/{id}/items` | Add a manual item |
| PATCH/DELETE | `/lists/{id}/items/{item_id}` | Check, edit, remove |
| POST | `/lists/{id}/finalize` | Mark shopping done, set `finalized_at` |
| GET | `/lists` | History of finalized lists |
| GET | `/suggestions` | Repeat-buy chips |
| GET/PATCH | `/settings` | `household_size` |

### Error handling

Errors return `{"detail": str, "code": str}` with an appropriate status.

- Deleting an ingredient referenced by any recipe returns 409 with the
  referencing recipe names in `detail`.
- Deleting a recipe referenced by any non-`done` plan returns 409 naming the
  weeks.
- Changing an ingredient's `unit` while any recipe references it returns 409.
- Entering a quantity in a unit outside the ingredient's family returns 422.
- Creating a `leftovers` meal whose source is invalid returns 422.

The frontend surfaces `detail` directly in a toast.

## Frontend

React + TypeScript + Vite. TanStack Query for all server state; no global
client state library. Desktop layout only.

### Recipes

Searchable list of recipe cards. Each opens the editor.

### Recipe editor

Name, serves, instructions, and ingredient rows. Each row begins with an
autocomplete over the ingredient catalog. Selecting an ingredient constrains
the quantity input to that ingredient's unit family via a unit dropdown; a
`count` ingredient shows a bare number labelled "whole".

Typing a name with no match offers inline ingredient creation: category
(which pre-selects a unit), unit, staple toggle. Created without leaving the
editor. This is the only place a unit is ever chosen.

### Ingredients

Table of the catalog: name, category, unit, staple flag, and a usage count.
Editable inline. Delete is disabled with a tooltip when the ingredient is in
use.

### Planner

A 7 × 3 grid, days as columns, meal slots as rows. Clicking an empty slot
opens a recipe search. If the chosen recipe is already cooked earlier that
week, "Leftovers of <day> <slot>" is offered as the first option.

Cook slots display an editable `servings_to_make`. Slots whose dependent
leftovers exceed the batch show an amber badge with an explanatory tooltip.
A "Generate shopping list" action sits below the grid.

### Shopping list

Items grouped by aisle with checkboxes, quantity, and name. Hovering a line
reveals its `contributions` — which recipes wanted it and how much.

Below the list: a manual-add input, suggestion chips, and the "Check your
seasonings" section listing staple ingredients this week's recipes use, with
the recipes named.

Actions: Regenerate, Print, Done shopping.

### Print

A dedicated print stylesheet hides navigation, buttons, and hover
affordances, producing one page of aisle-grouped items with hollow
checkboxes at a legible size.

### History

Finalized lists in reverse chronological order, each opening read-only with
its week and what was checked versus skipped.

## Project Layout

```
KatKitchen/
  backend/
    app/
      main.py db.py models.py schemas.py
      routers/    ingredients.py recipes.py plans.py lists.py settings.py
      services/   units.py list_builder.py suggestions.py
    tests/
    pyproject.toml
  frontend/
    src/
      api/ types/ components/
      pages/  Recipes/ RecipeEditor/ Ingredients/ Planner/ ShoppingList/ History/
      print.css
    package.json
  data/katkitchen.db
  docs/superpowers/specs/
  dev.ps1
  README.md
```

`dev.ps1` starts uvicorn and Vite together; Vite proxies `/api` to the backend.

## Testing Strategy

Test-driven throughout.

**Backend (pytest).** The pure services carry the real coverage:

- `units.py` — every accepted entry unit converts exactly to canonical;
  cross-family conversion raises; display formatting picks kg/l at the
  threshold.
- `list_builder.py` — scaling by servings; summing across recipes; round-up
  behavior at boundaries; staples partitioned out; leftover meals excluded;
  contributions recorded accurately.
- Regeneration — manual items survive; checkmarks survive a quantity change;
  orphaned recipe items are removed; manual items are never removed.
- `suggestions.py` — the 3-of-4 threshold, and exclusion of items already
  on the list.

Routers are tested via `TestClient` against in-memory SQLite, focused on
status codes and the referential-integrity refusals.

**Frontend (Vitest + Testing Library).** Only the parts with logic: the
recipe editor constraining units to the selected ingredient and creating
ingredients inline, and the planner offering leftovers for an
already-cooked recipe. No snapshot tests.

## Success Criteria

1. A recipe can be entered with structured amounts in under a minute, creating
   new ingredients inline without leaving the page.
2. A full week can be planned, including leftovers, without double-counting
   ingredients.
3. The generated list groups by aisle, sums correctly across recipes, and
   never rounds down.
4. Editing the plan after generating the list preserves every manual addition
   and checkmark.
5. The printed list is legible and usable one-handed in a store.
6. Past weeks remain viewable and drive repeat-buy suggestions.
