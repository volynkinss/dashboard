from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ServiceAccess(Base, TimestampMixin):
    __tablename__ = "service_access"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    access_group_id: Mapped[int] = mapped_column(ForeignKey("access_groups.id", ondelete="CASCADE"), primary_key=True)

    service = relationship("Service", back_populates="service_access")
    access_group = relationship("AccessGroup", back_populates="service_access")
