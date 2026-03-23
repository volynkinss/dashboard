from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.i18n import localize_text
from app.models.access_group import AccessGroup, AccessGroupSource
from app.models.category import Category
from app.models.category_access import CategoryAccess
from app.models.service import Service
from app.models.service_access import ServiceAccess


@dataclass(slots=True)
class ServiceView:
    slug: str
    name: str
    description: str | None
    url: str
    icon_url: str | None
    icon_emoji: str | None


@dataclass(slots=True)
class CategoryView:
    name: str
    slug: str
    aliases: tuple[str, ...]
    services: list[ServiceView]


class AccessControlService:
    def _resolve_matched_group_ids(self, db: Session, roles: set[str], groups: set[str]) -> set[int]:
        filters = []

        if roles:
            filters.append(
                and_(
                    AccessGroup.source == AccessGroupSource.CLIENT_ROLE,
                    AccessGroup.name.in_(roles),
                )
            )

        if groups:
            filters.append(
                and_(
                    AccessGroup.source == AccessGroupSource.GROUP,
                    AccessGroup.name.in_(groups),
                )
            )

        if not filters:
            return set()

        stmt = select(AccessGroup.id).where(AccessGroup.is_active.is_(True), or_(*filters))
        rows = db.execute(stmt).all()
        return {int(row[0]) for row in rows}

    def get_visible_catalog(self, db: Session, *, roles: set[str], groups: set[str], lang: str = "ru") -> list[CategoryView]:
        matched_group_ids = self._resolve_matched_group_ids(db, roles, groups)

        category_access_exists = exists(
            select(CategoryAccess.category_id).where(
                CategoryAccess.category_id == Category.id,
                CategoryAccess.access_group_id.in_(matched_group_ids),
            )
        )

        category_condition = Category.allow_all_authenticated.is_(True)
        if matched_group_ids:
            category_condition = or_(category_condition, category_access_exists)

        categories_stmt = (
            select(Category)
            .where(
                Category.is_active.is_(True),
                category_condition,
            )
            .order_by(Category.sort_order.asc(), Category.name.asc())
        )
        categories = list(db.scalars(categories_stmt))
        if not categories:
            return []

        category_ids = [category.id for category in categories]

        service_access_exists = exists(
            select(ServiceAccess.service_id).where(
                ServiceAccess.service_id == Service.id,
                ServiceAccess.access_group_id.in_(matched_group_ids),
            )
        )

        service_condition = Service.allow_all_authenticated.is_(True)
        if matched_group_ids:
            service_condition = or_(service_condition, service_access_exists)

        services_stmt = (
            select(Service)
            .where(
                Service.is_active.is_(True),
                Service.category_id.in_(category_ids),
                service_condition,
            )
            .order_by(Service.category_id.asc(), Service.sort_order.asc(), Service.name.asc())
        )
        services = list(db.scalars(services_stmt))

        services_by_category: dict[int, list[ServiceView]] = defaultdict(list)
        for service in services:
            localized_name = localize_text(service.name, service.name_i18n, lang) or service.name
            localized_description = localize_text(service.description, service.description_i18n, lang)
            services_by_category[service.category_id].append(
                ServiceView(
                    slug=service.slug,
                    name=localized_name,
                    description=localized_description,
                    url=service.url,
                    icon_url=service.icon_url,
                    icon_emoji=service.icon_emoji,
                )
            )

        result: list[CategoryView] = []
        for category in categories:
            category_services = services_by_category.get(category.id, [])
            if not category_services:
                continue

            localized_category_name = localize_text(category.name, category.name_i18n, lang) or category.name
            alias_values = [category.name]
            if category.name_i18n:
                alias_values.extend(category.name_i18n.values())
            alias_values.append(localized_category_name)
            unique_aliases = tuple(dict.fromkeys(value.strip() for value in alias_values if value and value.strip()))
            result.append(
                CategoryView(
                    name=localized_category_name,
                    slug=category.slug,
                    aliases=unique_aliases,
                    services=category_services,
                )
            )

        return result
