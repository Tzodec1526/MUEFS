from sqlalchemy import text

from alembic import op

revision = "d4e7a12b93f0"
down_revision = "c3d9f06a21b8"
branch_labels = None
depends_on = None

INDEXES = (
    ("cases", "case_number", "ix_cases_case_number", "ix_cases_case_number_trgm"),
    (
        "case_participants", "party_name", "ix_case_participants_party_name",
        "ix_case_participants_party_name_trgm",
    ),
)


def concurrent_index(name: str, table: str, column: str, *, trigram: bool) -> None:
    valid = op.get_bind().scalar(text("""
        SELECT i.indisvalid FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema() AND c.relname = :name
    """), {"name": name})
    if valid is True:
        return
    if valid is False:
        op.drop_index(name, postgresql_concurrently=True)
    options = (
        {"postgresql_using": "gin", "postgresql_ops": {column: "public.gin_trgm_ops"}}
        if trigram else {}
    )
    op.create_index(name, table, [column], postgresql_concurrently=True, **options)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        for _table, _column, old, _new in INDEXES:
            op.drop_index(old, if_exists=True)
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    extension_schema = op.get_bind().scalar(text("""
        SELECT n.nspname FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_trgm'
    """))
    if extension_schema != "public":
        raise RuntimeError(
            "MUEFS requires pg_trgm in the public schema. Ask the database administrator "
            "to configure it before upgrading; this migration will not move an existing extension."
        )
    with op.get_context().autocommit_block():
        for table, column, old, new in INDEXES:
            concurrent_index(new, table, column, trigram=True)
            op.drop_index(old, if_exists=True, postgresql_concurrently=True)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        for table, column, old, _new in INDEXES:
            op.create_index(old, table, [column], if_not_exists=True)
        return
    with op.get_context().autocommit_block():
        for table, column, old, new in INDEXES:
            concurrent_index(old, table, column, trigram=False)
            op.drop_index(new, if_exists=True, postgresql_concurrently=True)
