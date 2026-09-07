"""Bound receipt-register reads to retained payment activity in the selected period."""

from contextlib import nullcontext

from sqlalchemy import text

from alembic import op

revision = "c39f64dbea05"
down_revision = "b28e53cad9f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block() if postgres else nullcontext():
        if postgres:
            valid = op.get_bind().scalar(text("""
                SELECT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = 'ix_filing_payment_activity'
            """))
            if valid is False:
                op.drop_index("ix_filing_payment_activity", postgresql_concurrently=True)
        predicate = text("event_type IN ('fee_payment_recorded', 'fee_payment_reversed')")
        op.create_index(
            "ix_filing_payment_activity", "filing_transactions",
            ["occurred_at", "filing_id", "id"], if_not_exists=True,
            postgresql_concurrently=postgres, postgresql_where=predicate, sqlite_where=predicate,
        )


def downgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block() if postgres else nullcontext():
        op.drop_index("ix_filing_payment_activity", if_exists=True,
                      postgresql_concurrently=postgres)
