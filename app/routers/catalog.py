from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n import LANG_COOKIE_NAME, get_messages, normalize_language
from app.security.network import is_request_from_internal_network
from app.security.session_store import get_authenticated_session
from app.services.access_control import AccessControlService, CategoryView
from app.services.audit import write_audit_event
from app.services.maintenance import run_periodic_db_maintenance

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _normalize_tokens(values: list[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


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
        },
    )
