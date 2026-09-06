"""Version filing and case dates for retained court-order decisions."""

import sqlalchemy as sa

from alembic import op

revision = "b2e4a8c19d70"
down_revision = "a71b03d9e6f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("filing_envelopes", "cases"):
        op.add_column(table, sa.Column(
            "filing_date_version", sa.Integer(), nullable=False, server_default="0",
        ))


def downgrade() -> None:
    raise RuntimeError(
        "Court-ordered filing dates cannot be downgraded automatically. "
        "Use the court's verified backup and recovery procedure."
    )
