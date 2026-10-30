import sqlalchemy as sa

from alembic import op

revision = "a7d2e4c81f36"
down_revision = "e6b3f0a72c95"
branch_labels = None
depends_on = None

FIRST_RECEIPT = """COALESCE(
    (SELECT MIN(occurred_at) FROM filing_transactions
     WHERE filing_id = filing_envelopes.id AND event_type = 'submitted'),
    submitted_at)"""


def upgrade() -> None:
    op.add_column("filing_envelopes", sa.Column("filed_at", sa.DateTime(timezone=True)))
    op.execute(
        f"UPDATE filing_envelopes SET filed_at = {FIRST_RECEIPT} WHERE submitted_at IS NOT NULL"
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text(
        f"SELECT EXISTS (SELECT 1 FROM filing_envelopes WHERE filed_at <> {FIRST_RECEIPT})"
    )):
        raise RuntimeError("Cannot discard a first receipt that no other record retains")
    op.drop_column("filing_envelopes", "filed_at")
