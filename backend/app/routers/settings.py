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
