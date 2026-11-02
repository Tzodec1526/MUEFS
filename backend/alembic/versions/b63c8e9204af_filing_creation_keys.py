from contextlib import nullcontext

import sqlalchemy as sa

from alembic import op

revision = "b63c8e9204af"
down_revision = "9d34e6a81c72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("filing_envelopes")
    }
    for name, size in (("creation_key", 36), ("creation_sha256", 64)):
        if name not in columns:
            op.add_column("filing_envelopes", sa.Column(name, sa.String(size), nullable=True))
    postgres = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block() if postgres else nullcontext():
        if postgres:
            valid = op.get_bind().scalar(sa.text("""
                SELECT i.indisvalid FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema() AND c.relname = 'uq_filing_creation_key'
            """))
            if valid is False:
                op.drop_index("uq_filing_creation_key", postgresql_concurrently=True)
        op.create_index(
            "uq_filing_creation_key", "filing_envelopes", ["filer_id", "creation_key"],
            unique=True, if_not_exists=True, postgresql_concurrently=postgres,
            postgresql_where=sa.text("creation_key IS NOT NULL"),
            sqlite_where=sa.text("creation_key IS NOT NULL"),
        )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM filing_envelopes WHERE creation_key IS NOT NULL)"
    )):
        raise RuntimeError("Cannot discard retained filing creation request keys")
    postgres = op.get_bind().dialect.name == "postgresql"
    with op.get_context().autocommit_block() if postgres else nullcontext():
        op.drop_index("uq_filing_creation_key", if_exists=True, postgresql_concurrently=postgres)
    op.drop_column("filing_envelopes", "creation_sha256")
    op.drop_column("filing_envelopes", "creation_key")
