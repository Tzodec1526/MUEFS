import sqlalchemy as sa

from alembic import op

revision = "f94c81e2b7d5"
down_revision = "e83f2c91a6d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_public_copies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id", sa.Integer(), sa.ForeignKey("filing_documents.id"), nullable=False
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("is_text_searchable", sa.Boolean(), nullable=False),
        sa.Column("pii_warnings", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_document_public_copies_history", "document_public_copies", ["document_id", "id"]
    )
    op.add_column(
        "filing_documents",
        sa.Column("access_version", sa.Integer(), server_default="0", nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.add_column("filing_documents", sa.Column("public_copy_id", sa.Integer()))
        op.create_foreign_key(
            "fk_document_public_copy",
            "filing_documents",
            "document_public_copies",
            ["public_copy_id"],
            ["id"],
        )
        op.execute("""CREATE FUNCTION protect_document_public_copies()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'document_public_copies is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER document_public_copies_append_only BEFORE UPDATE OR DELETE
            ON document_public_copies FOR EACH ROW
            EXECUTE FUNCTION protect_document_public_copies()""")
    else:
        op.execute(
            "ALTER TABLE filing_documents ADD COLUMN public_copy_id INTEGER "
            "REFERENCES document_public_copies(id)"
        )
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER document_public_copies_no_{operation.lower()}
                BEFORE {operation} ON document_public_copies
                BEGIN SELECT RAISE(ABORT, 'document_public_copies is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError("Retained public copies cannot be downgraded automatically")
