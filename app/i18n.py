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
        "reload_config": "Обновить конфигурацию",
        "reload_config_success": "Конфигурация обновлена из dashy.yaml",
        "reload_config_busy": "Обновление уже выполняется, попробуйте чуть позже",
        "reload_config_error": "Не удалось обновить конфигурацию",
        "sign_out": "Выйти",
        "theme_switch_to_alt": "Другое оформление",
        "theme_switch_to_default": "Стандартное оформление",
        "no_services_title": "Сервисы недоступны",
        "no_services_body": "Для вашего аккаунта пока не назначены ярлыки.",
    },
    "en": {
        "search_label": "Search",
        "search_placeholder": "Type to filter services",
        "reload_config": "Reload config",
        "reload_config_success": "Configuration has been reloaded from dashy.yaml",
        "reload_config_busy": "Reload is already running, try again in a moment",
        "reload_config_error": "Could not reload configuration",
        "sign_out": "Sign out",
        "theme_switch_to_alt": "Alternative theme",
        "theme_switch_to_default": "Default theme",
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


def localize_text(
    default_text: str | None,
    localized_values: dict[str, str] | None,
    lang: str,
) -> str | None:
    normalized_lang = normalize_language(lang)

    if localized_values:
        for key in (normalized_lang, DEFAULT_LANGUAGE, "en"):
            value = localized_values.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped

        for value in localized_values.values():
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped

    if isinstance(default_text, str):
        stripped = default_text.strip()
        if stripped:
            return stripped
    return default_text
