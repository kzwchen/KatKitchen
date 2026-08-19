# KatKitchen

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
