"""Add headline field to user_details.

Revision ID: 20260808_0004
Revises: 20260808_0003
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0004"
down_revision: str | None = "20260808_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable headline column for parsed resume professional titles."""
    op.add_column(
        "user_details",
        sa.Column("headline", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Remove headline column from user_details."""
    op.drop_column("user_details", "headline")
