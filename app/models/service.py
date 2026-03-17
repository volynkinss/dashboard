from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Service(Base, TimestampMixin):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    name_i18n: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_i18n: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    icon_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_all_authenticated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category = relationship("Category", back_populates="services")
    service_access = relationship("ServiceAccess", back_populates="service", cascade="all, delete-orphan")
