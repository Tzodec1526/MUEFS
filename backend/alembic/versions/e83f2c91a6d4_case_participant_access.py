import sqlalchemy as sa

from alembic import op

revision = "e83f2c91a6d4"
down_revision = "d26e49b73c18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute("ALTER TYPE participantrole ADD VALUE IF NOT EXISTS 'ATTORNEY'")
    op.add_column(
        "cases", sa.Column("participant_version", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("case_participants", sa.Column("represented_party_name", sa.String(255)))
    op.add_column(
        "case_participants",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "case_participants",
        sa.Column("access_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("case_participants", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_index("ix_cases_court_id_id", "cases", ["court_id", "id"])
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")])
    participants = sa.table("case_participants", sa.column("case_id", sa.Integer()))
    audit = sa.table(
        "audit_log",
        sa.column("action", sa.String()),
        sa.column("entity_type", sa.String()),
        sa.column("entity_id", sa.Integer()),
        sa.column("details", sa.JSON()),
    )
    json_object = (
        sa.func.json_build_object
        if connection.dialect.name == "postgresql"
        else sa.func.json_object
    )
    connection.execute(
        audit.insert().from_select(
            ["action", "entity_type", "entity_id", "details"],
            sa.select(
                sa.literal("case.participants_review_required"),
                sa.literal("case"),
                participants.c.case_id,
                json_object(
                    "participant_count",
                    sa.func.count(),
                    "reason",
                    "Legacy participant records retained; court review required "
                    "before access is granted",
                ),
            ).group_by(participants.c.case_id),
        )
    )


def downgrade() -> None:
    raise RuntimeError("Participant access history cannot be downgraded automatically")
