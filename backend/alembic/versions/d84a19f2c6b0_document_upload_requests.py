"""Retain completed upload requests so lost responses can be retried safely."""

import sqlalchemy as sa

from alembic import op

revision = "d84a19f2c6b0"
down_revision = "c72d9fa083b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_upload_requests",
        sa.Column("envelope_id", sa.Integer(), sa.ForeignKey("filing_envelopes.id"),
                  primary_key=True),
        sa.Column("key", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("document_id", sa.Integer(),
                  sa.ForeignKey("filing_documents.id", ondelete="SET NULL"), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM document_upload_requests)")):
        raise RuntimeError("Cannot discard retained document upload requests")
    op.drop_table("document_upload_requests")
