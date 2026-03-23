from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n import LANG_COOKIE_NAME, get_messages, normalize_language
from app.security.csrf import validate_csrf_token
from app.security.network import is_request_from_internal_network
from app.security.session_store import get_authenticated_session
from app.services.access_control import AccessControlService, CategoryView
from app.services.activity_log import write_activity_event
from app.services.audit import write_audit_event
from app.services.config_reload import (
    ConfigReloadError,
    ConfigReloadInProgressError,
    reload_config_from_dashy,
)
from app.services.maintenance import run_periodic_db_maintenance

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
logger = logging.getLogger(__name__)


class ServiceClickEventPayload(BaseModel):
    csrf_token: str = Field(min_length=1, max_length=128)
    service_slug: str = Field(min_length=1, max_length=64)
    category_slug: str | None = Field(default=None, max_length=64)


def _normalize_tokens(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _can_reload_config(*, user_email: str | None, admin_email: str | None) -> bool:
    normalized_admin = _normalize_email(admin_email)
    normalized_user = _normalize_email(user_email)
    return bool(normalized_admin and normalized_user and normalized_user == normalized_admin)


def _sanitize_next_path(next_path: str | None) -> str:
    if not next_path:
        return "/"
    if not next_path.startswith("/"):
        return "/"
    if next_path.startswith("//"):
        return "/"
    return next_path


def _with_reload_result(next_path: str, result: str) -> str:
    separator = "&" if "?" in next_path else "?"
    return f"{next_path}{separator}config_reload={result}"


def _resolve_reload_status_message(*, status_value: str | None, ui: dict[str, str]) -> tuple[str | None, str | None]:
    if status_value == "ok":
        return "success", ui["reload_config_success"]
    if status_value == "busy":
        return "warning", ui["reload_config_busy"]
    if status_value == "error":
        return "error", ui["reload_config_error"]
    return None, None


def _filter_sections_for_external_clients(
    sections: list[CategoryView],
    *,
    is_internal_client: bool,
    internal_only_names: list[str],
    internal_only_slugs: list[str],
) -> list[CategoryView]:
    if is_internal_client:
        return sections

    blocked_names = _normalize_tokens(internal_only_names)
    blocked_slugs = _normalize_tokens(internal_only_slugs)

    if not blocked_names and not blocked_slugs:
        return sections

    filtered_sections: list[CategoryView] = []
    for section in sections:
        section_slug = section.slug.casefold()
        section_aliases = _normalize_tokens(list(section.aliases) + [section.name])
        if section_slug in blocked_slugs or section_aliases.intersection(blocked_names):
            continue
        filtered_sections.append(section)

    return filtered_sections


def _is_time_section(section: CategoryView) -> bool:
    return any(service.url.startswith("clock://") for service in section.services)


def _split_time_sections(sections: list[CategoryView]) -> tuple[list[CategoryView], list[CategoryView]]:
    regular_sections: list[CategoryView] = []
    time_sections: list[CategoryView] = []
    for section in sections:
        if _is_time_section(section):
            time_sections.append(section)
        else:
            regular_sections.append(section)
    return regular_sections, time_sections


@router.post("/events/service-click", status_code=status.HTTP_204_NO_CONTENT)
def service_click_event(payload: ServiceClickEventPayload, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not settings.activity_log_enabled:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    session_id = request.cookies.get(settings.session_cookie_name)
    user = get_authenticated_session(db, session_id)
    if user is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if not validate_csrf_token(user.csrf_token, payload.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    write_activity_event(
        event_type="service_click",
        request=request,
        user=user,
        details={
            "service_slug": payload.service_slug,
            "category_slug": payload.category_slug,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    run_periodic_db_maintenance()
    selected_lang = normalize_language(request.cookies.get(LANG_COOKIE_NAME))
    ui = get_messages(selected_lang)

    current_path = request.url.path
    if request.url.query:
        current_path = f"{current_path}?{request.url.query}"
    force_login_requested = request.query_params.get("force_login", "").strip().lower() in {"1", "true", "yes", "on"}

    session_id = request.cookies.get(settings.session_cookie_name)
    user = get_authenticated_session(db, session_id)

    if user is None:
        login_query = {"next": current_path}
        if (force_login_requested or session_id) and not settings.is_mock_auth_mode:
            login_query["force_login"] = "1"
        query = urlencode(login_query)
        return RedirectResponse(url=f"/auth/login?{query}", status_code=303)

    access_control = AccessControlService()
    sections = access_control.get_visible_catalog(db, roles=user.roles, groups=user.groups, lang=selected_lang)
    is_internal_client = is_request_from_internal_network(
        request,
        internal_networks=settings.internal_networks_list,
        trusted_proxy_networks=settings.trusted_proxy_networks_list,
    )
    sections = _filter_sections_for_external_clients(
        sections,
        is_internal_client=is_internal_client,
        internal_only_names=settings.internal_only_category_names_list,
        internal_only_slugs=settings.internal_only_category_slugs_list,
    )
    regular_sections, time_sections = _split_time_sections(sections)
    can_reload_config = _can_reload_config(user_email=user.email, admin_email=settings.admin_email_normalized)
    reload_status, reload_status_message = _resolve_reload_status_message(
        status_value=request.query_params.get("config_reload"),
        ui=ui,
    )
    if not can_reload_config:
        reload_status = None
        reload_status_message = None

    write_audit_event(db, event_type="catalog_view", request=request, user=user)

    return templates.TemplateResponse(
        "catalog.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "username": user.username,
            "sections": sections,
            "regular_sections": regular_sections,
            "time_sections": time_sections,
            "has_time_sections": bool(time_sections),
            "csrf_token": user.csrf_token,
            "lang": selected_lang,
            "ui": ui,
            "lang_ru_url": f"/lang/ru?{urlencode({'next': current_path})}",
            "lang_en_url": f"/lang/en?{urlencode({'next': current_path})}",
            "can_reload_config": can_reload_config,
            "config_reload_action_url": "/config/reload?next=%2F",
            "config_reload_status": reload_status,
            "config_reload_status_message": reload_status_message,
        },
    )


@router.post("/config/reload")
async def reload_config(
    request: Request,
    next: str | None = Query(default="/"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    run_periodic_db_maintenance()
    safe_next = _sanitize_next_path(next)

    session_id = request.cookies.get(settings.session_cookie_name)
    user = get_authenticated_session(db, session_id)
    if user is None:
        query = urlencode({"next": safe_next})
        return RedirectResponse(url=f"/auth/login?{query}", status_code=303)

    if not _can_reload_config(user_email=user.email, admin_email=settings.admin_email_normalized):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Config reload is not allowed")

    form = await request.form()
    csrf_token = form.get("csrf_token")
    if not validate_csrf_token(user.csrf_token, str(csrf_token) if csrf_token is not None else None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    try:
        reload_config_from_dashy(
            config_path=settings.dashy_config_path,
            deactivate_missing=True,
        )
    except ConfigReloadInProgressError:
        write_audit_event(db, event_type="config_reload_busy", request=request, user=user)
        return RedirectResponse(url=_with_reload_result(safe_next, "busy"), status_code=303)
    except ConfigReloadError as exc:
        logger.warning("Dashy config reload failed: %s", exc)
        write_audit_event(
            db,
            event_type="config_reload_failure",
            request=request,
            user=user,
            details={"error": str(exc)},
        )
        return RedirectResponse(url=_with_reload_result(safe_next, "error"), status_code=303)
    except Exception as exc:
        logger.exception("Unexpected error while reloading dashy config")
        write_audit_event(
            db,
            event_type="config_reload_failure",
            request=request,
            user=user,
            details={"error": str(exc)},
        )
        return RedirectResponse(url=_with_reload_result(safe_next, "error"), status_code=303)

    write_audit_event(db, event_type="config_reload_success", request=request, user=user)
    return RedirectResponse(url=_with_reload_result(safe_next, "ok"), status_code=303)
