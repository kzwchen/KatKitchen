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
