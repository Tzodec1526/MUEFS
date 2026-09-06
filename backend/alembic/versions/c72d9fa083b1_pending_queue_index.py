"""Read pending filings in receipt order without sorting both review statuses."""

from contextlib import nullcontext

from sqlalchemy import text

from alembic import op

revision = "c72d9fa083b1"
down_revision = "b63c8e9204af"
branch_labels = None
depends_on = None


def replace_index(old: str, new: str, columns: list[str], *, pending: bool = False) -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block() if postgres else nullcontext():
        if postgres:
            valid = op.get_bind().scalar(text("""
                SELECT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = :name
            """), {"name": new})
            if valid is False:
                op.drop_index(new, postgresql_concurrently=True)
        predicate = text("status IN ('SUBMITTED', 'UNDER_REVIEW')") if pending else None
        op.create_index(
            new, "filing_envelopes", columns, if_not_exists=True,
            postgresql_concurrently=postgres, postgresql_where=predicate, sqlite_where=predicate,
        )
        # The existing court/status/submitted index still covers general status queries.
        op.drop_index(old, if_exists=True, postgresql_concurrently=postgres)


def upgrade() -> None:
    replace_index(
        "ix_filing_court_status", "ix_filing_pending_received",
        ["court_id", "submitted_at", "id", "status"], pending=True,
    )


def downgrade() -> None:
    replace_index("ix_filing_pending_received", "ix_filing_court_status", ["court_id", "status"])
