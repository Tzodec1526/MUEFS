"""Retain document packages and recipients separately from relay outcomes."""

import sqlalchemy as sa

from alembic import op

revision = "f7a21b84d903"
down_revision = "a63b29d5e104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_packets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("filing_id", sa.Integer(), sa.ForeignKey("filing_envelopes.id"), nullable=False),
        sa.Column(
            "source_transaction_id",
            sa.String(36),
            sa.ForeignKey("filing_transactions.id"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_service_packet_key"),
    )
    op.create_index(
        "ix_service_packets_filing", "service_packets", ["filing_id", "created_at", "id"]
    )
    op.create_index("ix_service_packets_case", "service_packets", ["case_id", "created_at", "id"])
    op.create_table(
        "service_recipients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("packet_id", sa.String(36), sa.ForeignKey("service_packets.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("service_contacts.id"), nullable=False),
        sa.Column("contact_version", sa.Integer(), nullable=False),
        sa.Column("contact_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "notification_id", sa.Integer(), sa.ForeignKey("notifications.id"), nullable=False
        ),
        sa.UniqueConstraint("packet_id", "recipient_id", name="uq_service_packet_recipient"),
        sa.UniqueConstraint("notification_id"),
    )
    op.create_index("ix_service_recipients_recipient_id", "service_recipients", ["recipient_id"])
    op.create_table(
        "service_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "service_recipient_id",
            sa.String(36),
            sa.ForeignKey("service_recipients.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_service_events_recipient", "service_events", ["service_recipient_id", "id"])
    for table in ("service_packets", "service_recipients", "service_events"):
        if op.get_bind().dialect.name == "sqlite":
            for operation in ("UPDATE", "DELETE"):
                op.execute(f"""CREATE TRIGGER {table}_no_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END""")
        else:
            op.execute(f"""CREATE FUNCTION protect_{table}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION '{table} is append-only'; END; $$""")
            op.execute(f"""CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION protect_{table}()""")


def downgrade() -> None:
    raise RuntimeError("Retained service transactions cannot be downgraded automatically")
