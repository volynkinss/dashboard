"""add i18n fields for categories and services

Revision ID: 0002_i18n_fields
Revises: 0001_initial_schema
Create Date: 2026-03-17 12:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_i18n_fields"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("name_i18n", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.add_column("services", sa.Column("name_i18n", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("services", sa.Column("description_i18n", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "description_i18n")
    op.drop_column("services", "name_i18n")

    op.drop_column("categories", "name_i18n")
