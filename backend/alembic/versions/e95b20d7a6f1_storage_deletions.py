"""Queue physical draft deletion in the transaction that removes its metadata."""

import sqlalchemy as sa

from alembic import op

revision = "e95b20d7a6f1"
down_revision = "d84a19f2c6b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_deletions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("envelope_id", sa.Integer(), nullable=False),
        sa.Column("file_key", sa.String(500), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(250)),
    )
    op.create_index("ix_storage_deletions_due", "storage_deletions", ["next_attempt_at", "id"])
    op.create_index("ix_filing_documents_file_key", "filing_documents", ["file_key"])
    op.create_index("ix_document_public_copies_file_key", "document_public_copies", ["file_key"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM storage_deletions)")):
        raise RuntimeError("Drain pending storage deletions before downgrading")
    op.drop_index("ix_document_public_copies_file_key", table_name="document_public_copies")
    op.drop_index("ix_filing_documents_file_key", table_name="filing_documents")
    op.drop_table("storage_deletions")
