"""Read the newest recipient notices without sorting the entire inbox."""

from contextlib import nullcontext

from sqlalchemy import text

from alembic import op

revision = "a17d42b9c8e3"
down_revision = "f06c31a8b7d2"
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
        op.create_index(new, "notifications", columns, if_not_exists=True,
                        postgresql_concurrently=postgres)
        # Keep the old index until its replacement has finished building.
        op.drop_index(old, if_exists=True, postgresql_concurrently=postgres)


def upgrade() -> None:
    replace_index("ix_notifications_recipient_id", "ix_notification_recipient_newest",
                  ["recipient_id", "created_at", "id"])


def downgrade() -> None:
    replace_index("ix_notification_recipient_newest", "ix_notifications_recipient_id",
                  ["recipient_id"])
