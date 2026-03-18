from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.security.csrf import validate_csrf_token
from app.security.oidc import OIDCError, get_oidc_client
from app.security.session_store import (
    AuthenticatedSession,
    PrincipalData,
    create_user_session,
    delete_user_session,
    get_authenticated_session,
)
from app.services.audit import write_audit_event
from app.services.maintenance import run_periodic_db_maintenance

router = APIRouter(prefix="/auth", tags=["auth"])
OIDC_ID_TOKEN_COOKIE_NAME = "oidc_id_token_hint"


def _build_login_state_serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt="oidc-login")


def _sanitize_next_path(next_path: str | None) -> str:
    if not next_path:
        return "/"
    if not next_path.startswith("/"):
        return "/"
    if next_path.startswith("//"):
        return "/"
    return next_path


def _with_force_login_query(url: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["force_login"] = "1"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _set_session_cookie(response: RedirectResponse, *, settings: Settings, session_id: str, ttl_seconds: int) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


def _set_id_token_hint_cookie(response: RedirectResponse, *, settings: Settings, id_token: str, ttl_seconds: int) -> None:
    response.set_cookie(
        key=OIDC_ID_TOKEN_COOKIE_NAME,
        value=id_token,
        max_age=ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


def _delete_id_token_hint_cookie(response: RedirectResponse, *, settings: Settings) -> None:
    response.delete_cookie(
        key=OIDC_ID_TOKEN_COOKIE_NAME,
        domain=settings.session_cookie_domain,
        path="/",
    )


def _normalize_mock_profile(value: str | None, default_value: str) -> str:
    selected = (value or default_value).strip().lower()
    if selected not in {"public", "restricted"}:
        return default_value.strip().lower() or "restricted"
    return selected


def _build_mock_principal(settings: Settings, profile: str) -> PrincipalData:
    now = datetime.now(timezone.utc)
    if profile == "public":
        user_sub = settings.mock_public_user_sub
        username = settings.mock_public_username
        email = settings.mock_public_email
        roles = set(settings.mock_public_roles_list)
        groups = set(settings.mock_public_groups_list)
    else:
        user_sub = settings.mock_user_sub
        username = settings.mock_username
        email = settings.mock_email
        roles = set(settings.mock_roles_list)
        groups = set(settings.mock_groups_list)

    return PrincipalData(
        user_sub=user_sub,
        username=username,
        email=email,
        roles=roles,
        groups=groups,
        expires_at=now + timedelta(seconds=max(60, settings.mock_session_ttl_seconds)),
    )


def _issue_session_response(
    *,
    db: Session,
    request: Request,
    settings: Settings,
    principal: PrincipalData,
    redirect_target: str,
    event_type: str,
) -> RedirectResponse:
    session = create_user_session(db, principal, autocommit=False)

    ttl_seconds = max(1, int((principal.expires_at - datetime.now(timezone.utc)).total_seconds()))
    response = RedirectResponse(url=redirect_target, status_code=303)
    _set_session_cookie(response, settings=settings, session_id=session.session_id, ttl_seconds=ttl_seconds)

    auth_session = AuthenticatedSession(
        session_id=session.session_id,
        user_sub=principal.user_sub,
        username=principal.username,
        email=principal.email,
        roles=set(principal.roles),
        groups=set(principal.groups),
        csrf_token=session.csrf_token,
        expires_at=principal.expires_at,
    )
    write_audit_event(
        db,
        event_type=event_type,
        request=request,
        user=auth_session,
        autocommit=False,
    )
    db.commit()

    return response


@router.get("/login")
async def login(
    request: Request,
    next: str | None = Query(default=None),
    mock_user: str | None = Query(default=None),
    force_login: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    run_periodic_db_maintenance()
    safe_next = _sanitize_next_path(next)

    if settings.is_mock_auth_mode:
        selected_profile = _normalize_mock_profile(mock_user, settings.mock_profile_default)
        principal = _build_mock_principal(settings, selected_profile)
        return _issue_session_response(
            db=db,
            request=request,
            settings=settings,
            principal=principal,
            redirect_target=safe_next,
            event_type=f"mock_login_success_{selected_profile}",
        )

    oidc_client = get_oidc_client()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)

    try:
        authorization_url = await oidc_client.build_authorization_url(
            state=state,
            nonce=nonce,
            prompt="login" if force_login else None,
        )
    except OIDCError as exc:
        write_audit_event(
            db,
            event_type="login_failure",
            request=request,
            details={"reason": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC provider is unavailable",
        ) from exc

    serializer = _build_login_state_serializer()
    signed_payload = serializer.dumps({"state": state, "nonce": nonce, "next": safe_next})

    response = RedirectResponse(url=authorization_url, status_code=302)
    response.set_cookie(
        key=settings.oidc_temp_cookie_name,
        value=signed_payload,
        max_age=settings.oidc_temp_cookie_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )
    return response


@router.get("/post-logout")
def post_logout_landing(next: str | None = Query(default="/")):
    safe_next = _sanitize_next_path(next)
    query = urlencode({"next": safe_next, "force_login": "1"})
    return RedirectResponse(url=f"/auth/login?{query}", status_code=303)


@router.get("/callback")
async def callback(
    request: Request,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    run_periodic_db_maintenance()
    if settings.is_mock_auth_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Callback is disabled in mock auth mode")

    serializer = _build_login_state_serializer()
    oidc_client = get_oidc_client()

    if error:
        details = {"error": error}
        if error_description:
            details["error_description"] = error_description
        write_audit_event(
            db,
            event_type="login_failure",
            request=request,
            details=details,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OIDC authorization failed: {error}",
        )

    if not state or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC callback is missing required parameters",
        )

    signed_cookie = request.cookies.get(settings.oidc_temp_cookie_name)
    if not signed_cookie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OIDC state cookie")

    try:
        state_payload = serializer.loads(signed_cookie, max_age=settings.oidc_temp_cookie_max_age_seconds)
    except SignatureExpired as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login session expired") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid login state") from exc

    cookie_state = state_payload.get("state")
    if not isinstance(cookie_state, str) or not hmac.compare_digest(cookie_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="State verification failed")

    nonce = state_payload.get("nonce")
    if not isinstance(nonce, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nonce is missing")

    try:
        token_response = await oidc_client.exchange_code_for_tokens(code=code)
        principal = await oidc_client.verify_and_parse(token_response, expected_nonce=nonce)
    except OIDCError as exc:
        write_audit_event(
            db,
            event_type="login_failure",
            request=request,
            details={"reason": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from exc

    if principal.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is already expired")

    redirect_target = _sanitize_next_path(state_payload.get("next"))
    response = _issue_session_response(
        db=db,
        request=request,
        settings=settings,
        principal=principal,
        redirect_target=redirect_target,
        event_type="login_success",
    )
    ttl_seconds = max(1, int((principal.expires_at - datetime.now(timezone.utc)).total_seconds()))
    id_token = token_response.get("id_token")
    if isinstance(id_token, str) and id_token:
        _set_id_token_hint_cookie(
            response,
            settings=settings,
            id_token=id_token,
            ttl_seconds=ttl_seconds,
        )
    response.delete_cookie(
        key=settings.oidc_temp_cookie_name,
        domain=settings.session_cookie_domain,
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    run_periodic_db_maintenance()
    force_login_target = f"{request.url_for('login')}?{urlencode({'next': '/', 'force_login': '1'})}"
    default_post_logout_target = f"{request.url_for('post_logout_landing')}?{urlencode({'next': '/'})}"

    async def resolve_logout_target() -> str:
        if settings.is_mock_auth_mode:
            return "/"

        oidc_client = get_oidc_client()
        id_token_hint = request.cookies.get(OIDC_ID_TOKEN_COOKIE_NAME)
        post_logout_redirect_uri = settings.keycloak_post_logout_redirect_uri.strip()
        if not post_logout_redirect_uri:
            post_logout_redirect_uri = default_post_logout_target
        post_logout_redirect_uri = _with_force_login_query(post_logout_redirect_uri)

        try:
            return await oidc_client.build_logout_url(
                post_logout_redirect_uri=post_logout_redirect_uri,
                id_token_hint=id_token_hint,
            )
        except OIDCError:
            return force_login_target

    session_id = request.cookies.get(settings.session_cookie_name)
    user = get_authenticated_session(db, session_id)
    if user is None:
        redirect_target = await resolve_logout_target()
        response = RedirectResponse(url=redirect_target, status_code=303)
        response.delete_cookie(
            key=settings.session_cookie_name,
            domain=settings.session_cookie_domain,
            path="/",
        )
        _delete_id_token_hint_cookie(response, settings=settings)
        return response

    form = await request.form()
    csrf_token = form.get("csrf_token")
    if not validate_csrf_token(user.csrf_token, str(csrf_token) if csrf_token is not None else None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    delete_user_session(db, user.session_id, autocommit=False)
    write_audit_event(db, event_type="logout", request=request, user=user, autocommit=False)
    db.commit()

    logout_target = await resolve_logout_target()

    response = RedirectResponse(url=logout_target, status_code=303)
    response.delete_cookie(
        key=settings.session_cookie_name,
        domain=settings.session_cookie_domain,
        path="/",
    )
    _delete_id_token_hint_cookie(response, settings=settings)
    return response
