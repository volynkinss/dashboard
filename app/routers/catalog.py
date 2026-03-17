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
from app.security.session_store import get_authenticated_session
from app.services.access_control import AccessControlService
from app.services.audit import write_audit_event

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
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

    write_audit_event(db, event_type="catalog_view", request=request, user=user)

    return templates.TemplateResponse(
        "catalog.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "username": user.username,
            "sections": sections,
            "csrf_token": user.csrf_token,
            "lang": selected_lang,
            "ui": ui,
            "lang_ru_url": f"/lang/ru?{urlencode({'next': current_path})}",
            "lang_en_url": f"/lang/en?{urlencode({'next': current_path})}",
        },
    )
