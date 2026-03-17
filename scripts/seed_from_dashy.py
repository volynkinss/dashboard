from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    project_root_value = str(project_root)
    if project_root_value not in sys.path:
        sys.path.insert(0, project_root_value)

import yaml
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models.access_group import AccessGroup, AccessGroupSource
from app.models.category import Category
from app.models.service import Service
from app.models.service_access import ServiceAccess

ICON_TOKENS = {
    "envelope": "MAIL",
    "comments": "CHAT",
    "video": "CAM",
    "life-ring": "HELP",
    "question": "FAQ",
    "address-book": "BOOK",
    "key": "KEY",
    "television": "TV",
    "windows": "WIN",
    "desktop": "PC",
    "globe": "WEB",
    "clock": "CLK",
}

SUPPORTED_I18N_KEYS = ("ru", "en")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Dashy YAML into SQL tables")
    parser.add_argument("--config", required=True, help="Path to Dashy YAML config")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Deactivate categories/services not present in config",
    )
    return parser.parse_args()


def slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:64]


def unique_slug(base_slug: str, used: set[str]) -> str:
    slug = base_slug
    suffix = 1
    while slug in used:
        suffix += 1
        suffix_token = f"-{suffix}"
        slug = f"{base_slug[: max(1, 64 - len(suffix_token))]}{suffix_token}"
    used.add(slug)
    return slug


def icon_symbol(icon_value: str | None, title: str) -> str:
    if icon_value:
        lowered = icon_value.lower()
        for token, symbol in ICON_TOKENS.items():
            if token in lowered:
                return symbol
        for token in lowered.split():
            if token.startswith("fa-"):
                normalized = token.replace("fa-", "")
                if normalized:
                    return normalized[:4].upper()
    letters = re.sub(r"[^A-Za-z0-9]", "", title)
    return (letters[:4] or "APP").upper()


def normalize_i18n_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}

    result: dict[str, str] = {}
    for raw_key, raw_text in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_text, str):
            continue
        key = raw_key.strip().lower()
        text = raw_text.strip()
        if key in SUPPORTED_I18N_KEYS and text:
            result[key] = text
    return result


def extract_text_and_i18n(value: object) -> tuple[str | None, dict[str, str] | None]:
    if isinstance(value, str):
        text = value.strip()
        return (text if text else None), None

    i18n_map = normalize_i18n_map(value)
    if not i18n_map:
        return None, None

    for key in ("ru", "en"):
        text = i18n_map.get(key)
        if text:
            return text, i18n_map
    first_value = next(iter(i18n_map.values()))
    return first_value, i18n_map


def get_or_create_access_group(db, group_name: str) -> AccessGroup:
    existing = db.scalar(
        select(AccessGroup).where(
            AccessGroup.source == AccessGroupSource.GROUP,
            AccessGroup.name == group_name,
        )
    )
    if existing:
        existing.is_active = True
        return existing

    item = AccessGroup(
        source=AccessGroupSource.GROUP,
        name=group_name,
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def upsert_category(
    db,
    *,
    slug: str,
    name: str,
    name_i18n: dict[str, str] | None,
    sort_order: int,
) -> Category:
    existing = db.scalar(select(Category).where(Category.slug == slug))
    if existing:
        existing.name = name
        existing.name_i18n = name_i18n
        existing.description = None
        existing.sort_order = sort_order
        existing.is_active = True
        existing.allow_all_authenticated = True
        return existing

    category = Category(
        slug=slug,
        name=name,
        name_i18n=name_i18n,
        description=None,
        sort_order=sort_order,
        is_active=True,
        allow_all_authenticated=True,
    )
    db.add(category)
    db.flush()
    return category


def upsert_service(
    db,
    *,
    slug: str,
    category_id: int,
    name: str,
    name_i18n: dict[str, str] | None,
    description: str | None,
    description_i18n: dict[str, str] | None,
    url: str,
    icon_code: str,
    sort_order: int,
    allow_all_authenticated: bool,
) -> Service:
    existing = db.scalar(select(Service).where(Service.slug == slug))
    if existing:
        existing.category_id = category_id
        existing.name = name
        existing.name_i18n = name_i18n
        existing.description = description
        existing.description_i18n = description_i18n
        existing.url = url
        existing.icon_emoji = icon_code
        existing.icon_url = None
        existing.sort_order = sort_order
        existing.allow_all_authenticated = allow_all_authenticated
        existing.is_active = True
        return existing

    service = Service(
        category_id=category_id,
        slug=slug,
        name=name,
        name_i18n=name_i18n,
        description=description,
        description_i18n=description_i18n,
        url=url,
        icon_emoji=icon_code,
        icon_url=None,
        sort_order=sort_order,
        allow_all_authenticated=allow_all_authenticated,
        is_active=True,
    )
    db.add(service)
    db.flush()
    return service


def extract_groups(item: dict) -> list[str]:
    display_data = item.get("displayData") if isinstance(item, dict) else None
    if not isinstance(display_data, dict):
        return []

    visibility = display_data.get("showForKeycloakUsers")
    if not isinstance(visibility, dict):
        return []

    groups = visibility.get("groups")
    if not isinstance(groups, list):
        return []

    return [str(group).strip() for group in groups if isinstance(group, str) and str(group).strip()]


def extract_clock_items(section: dict) -> list[dict]:
    widgets = section.get("widgets")
    if not isinstance(widgets, list):
        return []

    result: list[dict] = []
    for index, widget in enumerate(widgets, start=1):
        if not isinstance(widget, dict):
            continue
        if widget.get("type") != "clock":
            continue

        options = widget.get("options")
        if not isinstance(options, dict):
            continue

        timezone = options.get("timeZone")
        if not isinstance(timezone, str) or not timezone.strip():
            continue

        label = timezone.split("/")[-1].replace("_", " ")
        result.append(
            {
                "title": label,
                "description": f"Clock for {timezone}",
                "icon": "fa fa-clock",
                "url": f"clock://{timezone}",
                "id": f"clock_{index}_{timezone}",
            }
        )

    return result


def deactivate_missing_entities(db, *, active_category_ids: set[int], active_service_ids: set[int]) -> None:
    for category in db.scalars(select(Category)).all():
        if category.id not in active_category_ids:
            category.is_active = False

    for service in db.scalars(select(Service)).all():
        if service.id not in active_service_ids:
            service.is_active = False


def import_config(config_path: Path, *, deactivate_missing: bool) -> None:
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise SystemExit("YAML does not contain valid 'sections' list")

    db = SessionLocal()
    try:
        used_category_slugs: set[str] = set()
        used_service_slugs: set[str] = set()

        active_category_ids: set[int] = set()
        active_service_ids: set[int] = set()

        for section_index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue

            section_name_value = section.get("name")
            section_name, section_name_i18n = extract_text_and_i18n(section_name_value)
            if not section_name:
                continue

            category_slug = unique_slug(
                slugify(section_name, f"section-{section_index}"),
                used_category_slugs,
            )
            category = upsert_category(
                db,
                slug=category_slug,
                name=section_name,
                name_i18n=section_name_i18n,
                sort_order=section_index * 10,
            )
            active_category_ids.add(category.id)

            items = section.get("items") if isinstance(section.get("items"), list) else []
            items = list(items) + extract_clock_items(section)

            for item_index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue

                item_title_value = item.get("title")
                item_url = item.get("url")
                item_title, item_title_i18n = extract_text_and_i18n(item_title_value)
                if not item_title:
                    continue
                if not isinstance(item_url, str) or not item_url.strip():
                    continue

                item_id = item.get("id")
                fallback_slug = f"item-{section_index}-{item_index}"
                raw_slug = str(item_id).strip() if isinstance(item_id, str) and item_id.strip() else item_title
                service_slug = unique_slug(slugify(raw_slug, fallback_slug), used_service_slugs)

                group_names = extract_groups(item)
                allow_all_authenticated = len(group_names) == 0
                item_description, item_description_i18n = extract_text_and_i18n(item.get("description"))

                service = upsert_service(
                    db,
                    slug=service_slug,
                    category_id=category.id,
                    name=item_title,
                    name_i18n=item_title_i18n,
                    description=item_description,
                    description_i18n=item_description_i18n,
                    url=item_url.strip(),
                    icon_code=icon_symbol(item.get("icon") if isinstance(item.get("icon"), str) else None, item_title),
                    sort_order=item_index * 10,
                    allow_all_authenticated=allow_all_authenticated,
                )
                active_service_ids.add(service.id)

                db.execute(delete(ServiceAccess).where(ServiceAccess.service_id == service.id))
                for group_name in group_names:
                    access_group = get_or_create_access_group(db, group_name)
                    db.add(ServiceAccess(service_id=service.id, access_group_id=access_group.id))

        if deactivate_missing:
            deactivate_missing_entities(
                db,
                active_category_ids=active_category_ids,
                active_service_ids=active_service_ids,
            )

        db.commit()
        print(f"Imported sections: {len(active_category_ids)}")
        print(f"Imported services: {len(active_service_ids)}")
    finally:
        db.close()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config does not exist: {config_path}")

    import_config(config_path, deactivate_missing=args.deactivate_missing)


if __name__ == "__main__":
    main()
