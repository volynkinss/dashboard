from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from datetime import time as datetime_time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

from starlette.requests import Request

from app.config import Settings, get_settings
from app.security.network import resolve_client_ip
from app.security.session_store import AuthenticatedSession

logger = logging.getLogger(__name__)

_activity_logger_lock = Lock()
_activity_logger: logging.Logger | None = None
_activity_logger_path: str | None = None
_activity_logger_failed_path: str | None = None
# Moscow is UTC+3 year-round; 00:00 MSK equals 21:00 UTC of the previous day.
_MSK_MIDNIGHT_UTC = datetime_time(hour=21, minute=0)


def _build_activity_logger(settings: Settings) -> logging.Logger:
    target_path = Path(settings.activity_log_file_path).expanduser()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    activity_logger = logging.getLogger("app.activity")
    existing_handlers = list(activity_logger.handlers)
    for handler in existing_handlers:
        activity_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = TimedRotatingFileHandler(
        filename=target_path,
        when="midnight",
        interval=1,
        backupCount=settings.activity_log_backup_count,
        encoding="utf-8",
        utc=True,
        atTime=_MSK_MIDNIGHT_UTC,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    activity_logger.addHandler(file_handler)
    activity_logger.setLevel(logging.INFO)
    activity_logger.propagate = False
    return activity_logger


def _get_activity_logger(settings: Settings) -> logging.Logger | None:
    global _activity_logger
    global _activity_logger_path
    global _activity_logger_failed_path

    if not settings.activity_log_enabled:
        return None

    configured_path = settings.activity_log_file_path.strip()
    if not configured_path:
        return None

    if _activity_logger is None and _activity_logger_failed_path == configured_path:
        return None

    with _activity_logger_lock:
        if _activity_logger is None and _activity_logger_failed_path == configured_path:
            return None

        if _activity_logger is None or _activity_logger_path != configured_path:
            try:
                _activity_logger = _build_activity_logger(settings)
                _activity_logger_path = configured_path
                _activity_logger_failed_path = None
            except Exception:
                logger.exception("Failed to configure activity logger for path: %s", configured_path)
                _activity_logger = None
                _activity_logger_path = configured_path
                _activity_logger_failed_path = configured_path
                return None

    return _activity_logger


def write_activity_event(
    *,
    event_type: str,
    request: Request,
    user: AuthenticatedSession | None = None,
    details: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> None:
    settings = get_settings()
    activity_logger = _get_activity_logger(settings)
    if activity_logger is None:
        return

    event_time = created_at or datetime.now(timezone.utc)
    resolved_ip = resolve_client_ip(
        request,
        trusted_proxy_networks=settings.trusted_proxy_networks_list,
    )
    ip_address = str(resolved_ip) if resolved_ip is not None else (request.client.host if request.client else None)

    payload: dict[str, Any] = {
        "ts": event_time.isoformat(),
        "event_type": event_type,
        "path": request.url.path,
        "method": request.method,
        "user_sub": user.user_sub if user else None,
        "username": user.username if user else None,
        "ip_address": ip_address,
        "user_agent": request.headers.get("user-agent"),
    }
    if details:
        payload["details"] = details

    try:
        activity_logger.info(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        )
    except Exception:
        logger.exception("Failed to write activity log event")
