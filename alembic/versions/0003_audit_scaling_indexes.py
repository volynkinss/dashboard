"""add indexes for audit retention and catalog view throttling

Revision ID: 0003_audit_scaling_indexes
Revises: 0002_i18n_fields
Create Date: 2026-03-17 15:20:00
"""

from __future__ import annotations

from alembic import op


revision = "0003_audit_scaling_indexes"
down_revision = "0002_i18n_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"], unique=False)
    op.create_index(
        "ix_audit_events_event_user_created_at",
        "audit_events",
        ["event_type", "user_sub", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_event_user_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
