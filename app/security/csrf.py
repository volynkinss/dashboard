from __future__ import annotations

import hmac
import secrets


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf_token(expected: str, received: str | None) -> bool:
    if not received:
        return False
    return hmac.compare_digest(expected, received)
