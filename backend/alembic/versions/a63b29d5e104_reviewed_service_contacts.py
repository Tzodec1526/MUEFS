import sqlalchemy as sa

from alembic import op

revision = "a63b29d5e104"
down_revision = "d4e7a12b93f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("service_contacts") as batch:
        batch.add_column(sa.Column("participant_id", sa.Integer()))
        batch.add_column(sa.Column("participant_snapshot", sa.JSON()))
        batch.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("authority", sa.String(1000)))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("reviewer_id", sa.Integer()))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key(
            "fk_service_contact_participant", "case_participants", ["participant_id"], ["id"]
        )
        batch.create_foreign_key("fk_service_contact_reviewer", "users", ["reviewer_id"], ["id"])
        batch.create_index("uq_service_contact_participant", ["participant_id"], unique=True)


def downgrade() -> None:
    raise RuntimeError(
        "Reviewed service instructions and authority cannot be downgraded automatically"
    )
