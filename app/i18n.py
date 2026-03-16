from __future__ import annotations

from typing import Final

SUPPORTED_LANGUAGES: Final[set[str]] = {"ru", "en"}
DEFAULT_LANGUAGE: Final[str] = "ru"
LANG_COOKIE_NAME: Final[str] = "catalog_lang"
LANG_COOKIE_MAX_AGE_SECONDS: Final[int] = 60 * 60 * 24 * 365

MESSAGES: Final[dict[str, dict[str, str]]] = {
    "ru": {
        "search_label": "Поиск",
        "search_placeholder": "Введите текст для фильтрации сервисов",
        "sign_out": "Выйти",
        "no_services_title": "Сервисы недоступны",
        "no_services_body": "Для вашего аккаунта пока не назначены ярлыки.",
    },
    "en": {
        "search_label": "Search",
        "search_placeholder": "Type to filter services",
        "sign_out": "Sign out",
        "no_services_title": "No services available",
        "no_services_body": "Your account has no granted shortcuts yet.",
    },
}


def normalize_language(value: str | None) -> str:
    if not value:
        return DEFAULT_LANGUAGE

    normalized = value.strip().lower()
    if normalized in SUPPORTED_LANGUAGES:
        return normalized

    return DEFAULT_LANGUAGE


def get_messages(lang: str) -> dict[str, str]:
    normalized_lang = normalize_language(lang)
    return MESSAGES[normalized_lang]
