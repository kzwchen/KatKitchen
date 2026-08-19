# KatKitchen — known issues carried past v1

Every item here was found by review during the build, judged not worth blocking
the merge, and re-triaged by the final whole-branch review, which confirmed 34 of
35 as acceptable to carry. None is a correctness bug in a path the app actually
uses today. They are recorded because "we knew" is worth more than rediscovering
them later, and because several are latent traps that only bite if someone
extends the code in a particular direction.

Nothing here needs doing before you use the app.

## The one open acceptance criterion

**Is the printed shopping list actually legible one-handed in a store?** This is
the only success criterion from the spec that was never verified. The print
stylesheet was measured under emulated print media — checkbox geometry, aisle
heading contrast, 12pt item text, page-break behaviour — but no human has held
the paper. Print a week and see.

## Latent traps — safe today, bite if extended

These are the ones worth reading before changing nearby code.

- **`ShoppingListItem.contributions` uses a plain JSON column**, which does not
  track in-place mutation. Safe only because the list builder reassigns the whole
  list. If anything ever `.append()`s to it, the change will not persist. Needs
  `MutableList.as_mutable` at that point.
- **`groupByCategory` keys groups by label.** Correct only because the backend
  sorts globally, so same-category items are always adjacent. If a query ever
  returns two non-adjacent runs sharing a category, React will see duplicate keys.
- **`round_up`'s `1e-9` epsilon is a judgment call.** If accumulated float drift
  in a very large weekly sum ever exceeds it, a quantity silently rounds down
  instead of up — which the spec forbids. No realistic list gets near it.
- **`Recipe.updated_at` has no `onupdate` hook**, so every write path must set it
  by hand. `update_recipe` does. A new write path that forgets will silently leave
  a stale timestamp.
- **`PATCH /recipes/{id}` treats `"lines": null` and an omitted `lines` the same.**
  To clear all lines a client must send `[]`. Undocumented in the API.

## Rough edges a user could notice

- Accepting a repeat-buy suggestion, or an inline category/staple edit on the
  Ingredients page, is not optimistic — the control can visibly snap back until
  the server responds.
- The meal-slot picker closes before its mutation resolves. If the slot was taken
  concurrently (409), the cell just shows `+` again with no explanation.
- The slot picker has no click-outside handler; only Escape or a successful pick
  closes it.
- `required` on the recipe name and serves inputs is dead markup — "Save recipe"
  is a `type=button`, so native constraint validation never fires. The attributes
  imply validation that does not run.

## Test-coverage gaps

Known holes, each stated as what would go unnoticed:

- No test proves an explicit `is_staple` overrides the category default; only the
  default path is covered.
- `test_same_category_items_are_alphabetical` compares "Apple" against "Onion",
  both title-case, so it would pass even if `sort_key`'s `.lower()` were removed.
  The name overstates what it proves.
- The round-once rounding test uses two meals of the *same* recipe, so it would
  not catch a variant that rounds per-recipe subtotals and then sums.
- No automated coverage of the edit-existing-recipe path, or of creating two
  ingredients in a row inline; both were verified only by hand in a browser.
- `groupByCategory` has no direct unit test despite two pages depending on it.
- The `cascade="all"` reach on `PlannedMeal.leftovers` is held by a single test,
  and covers a shape the API cannot currently produce.

## Performance

Several N+1 query patterns, all inherited from the implementation plan and all
bounded by single-user data volumes: `list_ingredients` (one usage count per
row), `list_recipes` and `_line_out` (per-line and per-collection lazy loads),
`list_plans` (one shopping-list query per plan), and the suggestions counter
(bounded by a 4-week window). At one household's scale these are microseconds.
They would matter if this ever became multi-tenant.

## Cosmetic / hygiene

- `frontend/src/index.css` is an empty, unimported leftover from the Vite
  scaffold.
- `frontend/README.md` is Vite boilerplate duplicating the root README.
- No `engines` field pins Node 20+ anywhere in the frontend.
- `backend/app/schemas.py` has mid-file imports (E402), a consequence of the
  append-only order it was built in.
- `import math` is unused in `backend/tests/test_units.py` (would trip ruff F401).
- `units.CANONICAL` is exported but never consumed internally — `round_up` and
  `format_display` hardcode `"count"`/`"g"`/`"ml"` instead of deriving from it.
  Same for the frontend's `UNIT_FAMILIES`, which no file imports.
- `round_up` and `format_display` raise a bare `KeyError` for a non-canonical
  unit, inconsistent with `family_of`/`to_canonical`, which raise `UnitError`.
- Patching only `servings_eaten` on a leftovers meal re-runs full leftovers
  validation including a fresh source fetch. Idempotent, just wasteful.

## Investigated and closed

Recorded so nobody re-opens them:

- **`RecipeEditorPage`'s edit-mode effect keying off `[existing]` object
  identity** was escalated through three reviews as a possible silent-overwrite
  risk. It is not one: `refetchOnWindowFocus` is off, TanStack Query's structural
  sharing returns the same reference for deep-equal payloads and `RecipeOut` omits
  `updated_at`, and nothing invalidates that query key while the editor is
  mounted. A clobber would need a second concurrent writer, where last-write-wins
  applies anyway.
- **`add_meal` does SELECT-then-INSERT** for slot uniqueness rather than catching
  the constraint. A concurrent duplicate would once have been a 500; the
  `IntegrityError` handler now returns a clean 409, so this is closed.
