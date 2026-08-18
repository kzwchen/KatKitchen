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
