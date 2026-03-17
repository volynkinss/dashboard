from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
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

    now = datetime.now(timezone.utc)
    if (
        event_type == "catalog_view"
        and user is not None
        and settings.audit_catalog_view_min_interval_seconds > 0
    ):
        recent_threshold = now - timedelta(seconds=settings.audit_catalog_view_min_interval_seconds)
        has_recent_catalog_view = db.scalar(
            select(AuditEvent.id)
            .where(
                AuditEvent.event_type == "catalog_view",
                AuditEvent.user_sub == user.user_sub,
                AuditEvent.created_at >= recent_threshold,
            )
            .limit(1)
        )
        if has_recent_catalog_view:
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
        created_at=now,
    )
    db.add(event)
    db.commit()
