"""Push-token registration for the mobile app."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PushToken
from ..schemas import PushTokenIn
from .deps import get_session, require_api_key

router = APIRouter(prefix="/push", tags=["push"], dependencies=[Depends(require_api_key)])


@router.post("/tokens", status_code=201)
def register_token(body: PushTokenIn, session: Session = Depends(get_session)):
    existing = session.execute(
        select(PushToken).where(PushToken.token == body.token)
    ).scalars().first()
    if existing is None:
        session.add(PushToken(token=body.token, platform=body.platform))
        session.commit()
    return {"ok": True}


@router.delete("/tokens", status_code=204)
def delete_token(token: str, session: Session = Depends(get_session)):
    existing = session.execute(
        select(PushToken).where(PushToken.token == token)
    ).scalars().first()
    if existing is not None:
        session.delete(existing)
        session.commit()
