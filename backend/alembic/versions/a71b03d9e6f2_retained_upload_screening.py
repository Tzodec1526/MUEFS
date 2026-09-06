"""Keep advisory upload screening without rereading every PDF during validation."""

import sqlalchemy as sa

from alembic import op

revision = "a71b03d9e6f2"
down_revision = "f94c81e2b7d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null distinguishes legacy documents without a recorded screening result from
    # an upload whose sampled scan found no warnings. Do not invent historical scans.
    op.add_column("filing_documents", sa.Column("pii_warnings", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Retained screening results cannot be downgraded automatically")
