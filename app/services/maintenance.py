from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Lock

from sqlalchemy import delete

from app.config import get_settings
from app.db import SessionLocal
from app.models.audit_event import AuditEvent
from app.models.user_session import UserSession

logger = logging.getLogger(__name__)

_maintenance_lock = Lock()
_next_run_at: datetime | None = None


def run_periodic_db_maintenance(*, force: bool = False) -> None:
    global _next_run_at

    settings = get_settings()
    if not settings.db_maintenance_enabled:
        return

    now = datetime.now(timezone.utc)
    if not force and _next_run_at and now < _next_run_at:
        return

    if not _maintenance_lock.acquire(blocking=False):
        return

    try:
        now = datetime.now(timezone.utc)
        if not force and _next_run_at and now < _next_run_at:
            return

        expired_before = now - timedelta(seconds=settings.session_expired_grace_seconds)
        audit_before = now - timedelta(days=settings.audit_retention_days)

        with SessionLocal() as db:
            deleted_sessions = db.execute(
                delete(UserSession).where(UserSession.expires_at < expired_before)
            ).rowcount or 0
            deleted_audits = db.execute(
                delete(AuditEvent).where(AuditEvent.created_at < audit_before)
            ).rowcount or 0
            db.commit()

        if deleted_sessions or deleted_audits:
            logger.info(
                "DB maintenance: deleted %s expired sessions and %s old audit events",
                deleted_sessions,
                deleted_audits,
            )
    except Exception:
        logger.exception("DB maintenance failed")
    finally:
        next_interval = max(30, settings.db_maintenance_interval_seconds)
        _next_run_at = datetime.now(timezone.utc) + timedelta(seconds=next_interval)
        _maintenance_lock.release()
