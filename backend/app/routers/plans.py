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


def _dependents(session: Session, meal_id: int) -> list[PlannedMeal]:
    """Leftover meals that point at meal_id as their source."""
    return session.exec(
        select(PlannedMeal).where(PlannedMeal.source_meal_id == meal_id)
    ).all()


def _raise_if_meal_has_leftovers(session: Session, meal_id: int) -> None:
    if _dependents(session, meal_id):
        raise AppError(
            409,
            "meal_has_leftovers",
            "Remove the leftover slots that point at this meal first",
        )


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

    # A cook meal that other slots point to as their source must stay a cook
    # of the same recipe, or those leftovers silently stop matching reality.
    if meal.kind is MealKind.COOK and (
        kind is not MealKind.COOK or recipe_id != meal.recipe_id
    ):
        _raise_if_meal_has_leftovers(session, meal_id)

    if kind is MealKind.LEFTOVERS:
        _validate_leftovers(
            session, meal.plan, meal.day, meal.slot, recipe_id, source_meal_id
        )
        changes["servings_to_make"] = None
    else:
        changes["source_meal_id"] = None
        effective_servings_to_make = changes.get(
            "servings_to_make", meal.servings_to_make
        )
        if effective_servings_to_make is None:
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
    _raise_if_meal_has_leftovers(session, meal_id)
    session.delete(meal)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
