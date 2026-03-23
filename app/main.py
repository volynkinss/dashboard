from __future__ import annotations

import logging
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.routers.auth import router as auth_router
from app.routers.catalog import router as catalog_router
from app.routers.i18n import router as i18n_router

settings = get_settings()

logging.basicConfig(level=settings.log_level)

app = FastAPI(title=settings.app_name)

if settings.trusted_hosts_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def _extract_origin(url: str) -> str | None:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_content_security_policy() -> str:
    form_action_sources = ["'self'"]
    style_sources = ["'self'"]
    font_sources = ["'self'"]

    if not settings.is_mock_auth_mode:
        keycloak_origin = _extract_origin(settings.keycloak_issuer_url)
        if keycloak_origin:
            form_action_sources.append(keycloak_origin)

    # Keep order deterministic and avoid duplicate origins.
    unique_form_action_sources = list(dict.fromkeys(form_action_sources))
    unique_style_sources = list(dict.fromkeys(style_sources))
    unique_font_sources = list(dict.fromkeys(font_sources))
    form_action = " ".join(unique_form_action_sources)
    style_src = " ".join(unique_style_sources)
    font_src = " ".join(unique_font_sources)

    return (
        "default-src 'self'; "
        "img-src 'self' https: data:; "
        f"style-src {style_src}; "
        f"font-src {font_src}; "
        "script-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        f"form-action {form_action}"
    )


CONTENT_SECURITY_POLICY = _build_content_security_policy()


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if settings.session_cookie_secure:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(i18n_router)
