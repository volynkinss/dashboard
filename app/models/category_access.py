from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class CategoryAccess(Base, TimestampMixin):
    __tablename__ = "category_access"

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    access_group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id", ondelete="CASCADE"), primary_key=True)

    category = relationship("Category", back_populates="category_access")
    access_group = relationship("AccessGroup", back_populates="category_access")
