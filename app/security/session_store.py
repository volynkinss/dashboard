from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user_session import UserSession
from app.security.csrf import generate_csrf_token


@dataclass(slots=True)
class AuthenticatedSession:
    session_id: str
    user_sub: str
    username: str
    email: str | None
    roles: set[str]
    groups: set[str]
    csrf_token: str
    expires_at: datetime


@dataclass(slots=True)
class PrincipalData:
    user_sub: str
    username: str
    email: str | None
    roles: set[str]
    groups: set[str]
    expires_at: datetime


def _build_authenticated_session(record: UserSession) -> AuthenticatedSession:
    return AuthenticatedSession(
        session_id=record.session_id,
        user_sub=record.user_sub,
        username=record.username,
        email=record.email,
        roles=set(record.roles_json or []),
        groups=set(record.groups_json or []),
        csrf_token=record.csrf_token,
        expires_at=record.expires_at,
    )


def create_user_session(db: Session, principal: PrincipalData, *, autocommit: bool = True) -> UserSession:
    now = datetime.now(timezone.utc)
    session = UserSession(
        session_id=secrets.token_urlsafe(48),
        user_sub=principal.user_sub,
        username=principal.username,
        email=principal.email,
        roles_json=sorted(principal.roles),
        groups_json=sorted(principal.groups),
        csrf_token=generate_csrf_token(),
        issued_at=now,
        expires_at=principal.expires_at,
        created_at=now,
        last_seen_at=now,
    )
    db.add(session)
    if autocommit:
        db.commit()
        db.refresh(session)
    else:
        db.flush()
    return session


def delete_user_session(db: Session, session_id: str, *, autocommit: bool = True) -> bool:
    record = db.get(UserSession, session_id)
    if record is None:
        return False
    db.delete(record)
    if autocommit:
        db.commit()
    return True


def get_authenticated_session(db: Session, session_id: str | None) -> AuthenticatedSession | None:
    if not session_id:
        return None

    record = db.get(UserSession, session_id)
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    if record.expires_at <= now:
        db.delete(record)
        db.commit()
        return None

    settings = get_settings()
    update_interval = max(0, settings.session_last_seen_update_interval_seconds)
    last_seen_at = record.last_seen_at
    should_update_last_seen = (
        update_interval == 0
        or last_seen_at is None
        or (now - last_seen_at).total_seconds() >= update_interval
    )
    if should_update_last_seen:
        record.last_seen_at = now
        db.commit()

    return _build_authenticated_session(record)
