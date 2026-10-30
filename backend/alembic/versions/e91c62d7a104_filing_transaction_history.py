import sqlalchemy as sa
from alembic import op

revision = "e91c62d7a104"
down_revision = "c4f8e2a91b0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filing_envelopes", sa.Column(
        "submission_count", sa.Integer(), server_default="0", nullable=False,
    ))
    op.add_column("filing_documents", sa.Column("retained_at", sa.DateTime(timezone=True)))
    op.add_column("filing_documents", sa.Column("removed_at", sa.DateTime(timezone=True)))
    op.execute("""UPDATE filing_documents SET retained_at = (
        SELECT submitted_at FROM filing_envelopes WHERE id = filing_documents.envelope_id
    )""")
    op.execute("""UPDATE filing_documents SET is_confidential = true
        WHERE document_type_code = 'FEE_WAIVER'""")
    op.create_table(
        "filing_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("filing_envelopes.id"), nullable=False),
        sa.Column("submission_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(36)),
        sa.UniqueConstraint("filing_id", "idempotency_key", name="uq_filing_submission_key"),
    )
    op.create_index("ix_filing_transactions_history", "filing_transactions",
                    ["filing_id", "occurred_at", "id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_filing_transactions() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'filing_transactions is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER filing_transactions_append_only BEFORE UPDATE OR DELETE
            ON filing_transactions FOR EACH ROW EXECUTE FUNCTION protect_filing_transactions()""")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER filing_transactions_no_{operation.lower()}
                BEFORE {operation} ON filing_transactions
                BEGIN SELECT RAISE(ABORT, 'filing_transactions is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError(
        "This migration retains court transactions and cannot be downgraded automatically. "
        "Restore a verified pre-migration backup only under the court's recovery procedure."
    )
