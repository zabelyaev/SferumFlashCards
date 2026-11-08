"""Remove the index duplicated by the user/date unique constraint.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_user_activity_recent", table_name="user_daily_activity")


def downgrade() -> None:
    op.create_index(
        "idx_user_activity_recent", "user_daily_activity", ["user_id", "activity_date"]
    )
