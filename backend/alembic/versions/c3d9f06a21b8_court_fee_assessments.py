import sqlalchemy as sa

from alembic import op

revision = "c3d9f06a21b8"
down_revision = "b2e4a8c19d70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("filing_envelopes") as batch:
        batch.add_column(sa.Column("fee_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("fee_review_requested_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("fee_assessment_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_filing_fee_assessment", "filing_transactions", ["fee_assessment_id"], ["id"]
        )
    op.create_index(
        "ix_filing_court_fee_review",
        "filing_envelopes",
        ["court_id", "fee_review_requested_at", "id"],
    )
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("envelope_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("fee_basis", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.create_foreign_key("fk_payment_envelope", "filing_envelopes", ["envelope_id"], ["id"])
        batch.create_index("ix_payments_envelope_id", ["envelope_id"])
    op.execute("""UPDATE payments SET envelope_id = (
        SELECT MIN(f.id) FROM filing_envelopes AS f
        WHERE f.payment_id = payments.id AND f.filer_id = payments.payer_id
        ) WHERE (SELECT COUNT(*) FROM filing_envelopes AS f
                 WHERE f.payment_id = payments.id) = 1""")


def downgrade() -> None:
    raise RuntimeError(
        "Retained fee assessments and payment allocations cannot be downgraded automatically. "
        "Use the court's verified backup and recovery procedure."
    )
