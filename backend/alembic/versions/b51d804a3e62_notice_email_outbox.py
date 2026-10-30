import sqlalchemy as sa

from alembic import op

revision = "b51d804a3e62"
down_revision = "a8b712e43c90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("verified_email", sa.String(255)))
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "notifications",
            "delivery_status",
            type_=sa.String(24),
            postgresql_using="delivery_status::text",
        )
    op.execute(
        "UPDATE notifications SET delivery_status='DISABLED' WHERE delivery_status='PENDING'"
    )
    for name in ("email_recipient", "email_sender", "email_message_id"):
        op.add_column("notifications", sa.Column(name, sa.String(255)))
    op.create_index(
        "ix_notification_message_id", "notifications", ["email_message_id"], unique=True
    )
    op.add_column("notifications", sa.Column("email_message", sa.Text()))
    op.add_column(
        "notifications",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("notifications", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("last_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("notifications", sa.Column("last_error", sa.String(1000)))
    op.create_index(
        "ix_notification_outbox", "notifications", ["delivery_status", "next_attempt_at", "id"]
    )
    op.create_table(
        "notification_delivery_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=False
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", sa.String(1000)),
        sa.Column("smtp_code", sa.Integer()),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("message", sa.Text()),
    )
    op.create_index(
        "ix_notification_delivery_events_notification_id",
        "notification_delivery_events",
        ["notification_id"],
    )
    op.execute("""INSERT INTO notification_delivery_events
        (notification_id, attempt_number, outcome, occurred_at, detail)
        SELECT id, 0, 'legacy_status', COALESCE(sent_at, created_at),
        'Pre-outbox status: ' || delivery_status
        FROM notifications WHERE delivery_status IN ('SENT', 'DELIVERED', 'FAILED')""")
    op.execute("""UPDATE notifications SET delivery_status='LEGACY'
        WHERE delivery_status IN ('SENT', 'DELIVERED', 'FAILED')""")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_notification_delivery_events() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION
            'notification_delivery_events is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER notification_delivery_events_append_only
            BEFORE UPDATE OR DELETE ON notification_delivery_events
            FOR EACH ROW EXECUTE FUNCTION protect_notification_delivery_events()""")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER notification_delivery_events_no_{operation.lower()}
                BEFORE {operation} ON notification_delivery_events
                BEGIN SELECT RAISE(ABORT, 'notification_delivery_events is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError("Retained notice attempts cannot be downgraded automatically")
