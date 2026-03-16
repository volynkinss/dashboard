from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session
from starlette.requests import Request

from app.config import get_settings
from app.models.audit_event import AuditEvent
from app.security.session_store import AuthenticatedSession


def write_audit_event(
    db: Session,
    *,
    event_type: str,
    request: Request,
    user: AuthenticatedSession | None = None,
    details: dict | None = None,
) -> None:
    settings = get_settings()
    if not settings.audit_enabled:
        return

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    event = AuditEvent(
        event_type=event_type,
        user_sub=user.user_sub if user else None,
        username=user.username if user else None,
        ip_address=ip_address,
        user_agent=user_agent,
        details_json=details,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
