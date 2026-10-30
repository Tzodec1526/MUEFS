from contextlib import nullcontext

from sqlalchemy import text

from alembic import op

revision = "9d34e6a81c72"
down_revision = "f7a21b84d903"
branch_labels = None
depends_on = None


def replace_index(old: str, new: str, columns: list[str]) -> None:
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
        op.create_index(
            new, "filing_envelopes", columns,
            if_not_exists=True, postgresql_concurrently=postgres,
        )
        op.drop_index(old, if_exists=True, postgresql_concurrently=postgres)


def upgrade() -> None:
    replace_index(
        "ix_filing_envelopes_filer_id", "ix_filing_filer_updated",
        ["filer_id", "updated_at", "id", "status"],
    )


def downgrade() -> None:
    replace_index(
        "ix_filing_filer_updated", "ix_filing_envelopes_filer_id", ["filer_id"],
    )
