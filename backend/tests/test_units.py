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
