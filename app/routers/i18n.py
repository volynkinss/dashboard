from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.i18n import LANG_COOKIE_MAX_AGE_SECONDS, LANG_COOKIE_NAME, normalize_language

router = APIRouter(tags=["i18n"])


def _sanitize_next_path(next_path: str | None) -> str:
    if not next_path:
        return "/"
    if not next_path.startswith("/"):
        return "/"
    if next_path.startswith("//"):
        return "/"
    return next_path


@router.get("/lang/{lang_code}")
def set_language(lang_code: str, next: str | None = Query(default="/")):
    settings = get_settings()
    selected_lang = normalize_language(lang_code)
    safe_next = _sanitize_next_path(next)

    response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=LANG_COOKIE_NAME,
        value=selected_lang,
        max_age=LANG_COOKIE_MAX_AGE_SECONDS,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        domain=settings.session_cookie_domain,
        path="/",
    )
    return response
