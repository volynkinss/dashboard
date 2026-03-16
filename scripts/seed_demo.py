from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    project_root_value = str(project_root)
    if project_root_value not in sys.path:
        sys.path.insert(0, project_root_value)

from sqlalchemy import select

from app.db import SessionLocal
from app.models.access_group import AccessGroup, AccessGroupSource
from app.models.category import Category
from app.models.category_access import CategoryAccess
from app.models.service import Service
from app.models.service_access import ServiceAccess


def get_or_create_access_group(db, source: AccessGroupSource, name: str) -> AccessGroup:
    existing = db.scalar(
        select(AccessGroup).where(
            AccessGroup.source == source,
            AccessGroup.name == name,
        )
    )
    if existing:
        existing.is_active = True
        return existing

    item = AccessGroup(source=source, name=name, is_active=True)
    db.add(item)
    db.flush()
    return item


def get_or_create_category(
    db,
    *,
    slug: str,
    name: str,
    description: str,
    allow_all_authenticated: bool,
    sort_order: int,
) -> Category:
    existing = db.scalar(select(Category).where(Category.slug == slug))
    if existing:
        existing.name = name
        existing.description = description
        existing.allow_all_authenticated = allow_all_authenticated
        existing.sort_order = sort_order
        existing.is_active = True
        return existing

    item = Category(
        slug=slug,
        name=name,
        description=description,
        allow_all_authenticated=allow_all_authenticated,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def get_or_create_service(
    db,
    *,
    category_id: int,
    slug: str,
    name: str,
    description: str,
    url: str,
    icon_emoji: str,
    allow_all_authenticated: bool,
    sort_order: int,
) -> Service:
    existing = db.scalar(select(Service).where(Service.slug == slug))
    if existing:
        existing.category_id = category_id
        existing.name = name
        existing.description = description
        existing.url = url
        existing.icon_emoji = icon_emoji
        existing.allow_all_authenticated = allow_all_authenticated
        existing.sort_order = sort_order
        existing.is_active = True
        return existing

    item = Service(
        category_id=category_id,
        slug=slug,
        name=name,
        description=description,
        url=url,
        icon_emoji=icon_emoji,
        allow_all_authenticated=allow_all_authenticated,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(item)
    db.flush()
    return item


def ensure_category_access(db, category_id: int, group_id: int) -> None:
    existing = db.get(CategoryAccess, {"category_id": category_id, "access_group_id": group_id})
    if existing is None:
        db.add(CategoryAccess(category_id=category_id, access_group_id=group_id))


def ensure_service_access(db, service_id: int, group_id: int) -> None:
    existing = db.get(ServiceAccess, {"service_id": service_id, "access_group_id": group_id})
    if existing is None:
        db.add(ServiceAccess(service_id=service_id, access_group_id=group_id))


def main() -> None:
    db = SessionLocal()
    try:
        role_catalog_user = get_or_create_access_group(db, AccessGroupSource.CLIENT_ROLE, "catalog-user")
        group_it_portal = get_or_create_access_group(db, AccessGroupSource.GROUP, "/AD/IT/PortalUsers")

        common = get_or_create_category(
            db,
            slug="common",
            name="Common",
            description="Common services for all authenticated users",
            allow_all_authenticated=True,
            sort_order=10,
        )
        engineering = get_or_create_category(
            db,
            slug="engineering",
            name="Engineering",
            description="Restricted engineering tools",
            allow_all_authenticated=False,
            sort_order=20,
        )

        jira = get_or_create_service(
            db,
            category_id=common.id,
            slug="jira",
            name="Jira",
            description="Issue tracking",
            url="https://jira.example.internal",
            icon_emoji="J",
            allow_all_authenticated=True,
            sort_order=10,
        )
        grafana = get_or_create_service(
            db,
            category_id=engineering.id,
            slug="grafana",
            name="Grafana",
            description="Metrics dashboards",
            url="https://grafana.example.internal",
            icon_emoji="G",
            allow_all_authenticated=False,
            sort_order=10,
        )
        gitlab = get_or_create_service(
            db,
            category_id=engineering.id,
            slug="gitlab",
            name="GitLab",
            description="Source control and CI",
            url="https://gitlab.example.internal",
            icon_emoji="GL",
            allow_all_authenticated=False,
            sort_order=20,
        )

        ensure_category_access(db, engineering.id, role_catalog_user.id)
        ensure_category_access(db, engineering.id, group_it_portal.id)

        ensure_service_access(db, grafana.id, role_catalog_user.id)
        ensure_service_access(db, grafana.id, group_it_portal.id)
        ensure_service_access(db, gitlab.id, role_catalog_user.id)
        ensure_service_access(db, gitlab.id, group_it_portal.id)

        db.commit()
        print("Demo seed completed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
