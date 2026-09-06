"""Version court intake publications without changing existing intake flags."""

import sqlalchemy as sa

from alembic import op

revision = "f06c31a8b7d2"
down_revision = "e95b20d7a6f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("courts", sa.Column("intake_version", sa.Integer(), nullable=False,
                                     server_default="0"))
    op.add_column("courts", sa.Column("intake_notice", sa.Text()))


def downgrade() -> None:
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM courts "
        "WHERE intake_version > 0 OR intake_notice IS NOT NULL)",
    )):
        raise RuntimeError("Cannot discard retained intake publications")
    op.drop_column("courts", "intake_notice")
    op.drop_column("courts", "intake_version")
