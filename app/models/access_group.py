from __future__ import annotations

from enum import Enum

from sqlalchemy import Boolean, Enum as SAEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AccessGroupSource(str, Enum):
    GROUP = "group"
    CLIENT_ROLE = "client_role"


class AccessGroup(Base, TimestampMixin):
    __tablename__ = "access_groups"
    __table_args__ = (
        UniqueConstraint("source", "name", name="uq_access_groups_source_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[AccessGroupSource] = mapped_column(
        SAEnum(
            AccessGroupSource,
            name="access_group_source",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    service_access = relationship("ServiceAccess", back_populates="access_group", cascade="all, delete-orphan")
    category_access = relationship("CategoryAccess", back_populates="access_group", cascade="all, delete-orphan")
