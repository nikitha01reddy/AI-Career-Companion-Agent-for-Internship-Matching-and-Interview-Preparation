"""Add linkedin contact field to user_details.

Revision ID: 20260808_0003
Revises: 20260805_0002
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260808_0003"
down_revision: str | None = "20260805_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable linkedin column for parsed resume contact data."""
    op.add_column(
        "user_details",
        sa.Column("linkedin", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Remove linkedin column from user_details."""
    op.drop_column("user_details", "linkedin")
