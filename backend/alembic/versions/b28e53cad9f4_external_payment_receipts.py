"""Retain external payment credits, reversals and independent payment review versions."""

import sqlalchemy as sa

from alembic import op

revision = "b28e53cad9f4"
down_revision = "a17d42b9c8e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'REVERSED'")
    op.add_column(
        "filing_envelopes",
        sa.Column("payment_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("payments", sa.Column("external_request_key", sa.String(36)))
    op.add_column("payments", sa.Column("external_receipt_key", sa.String(64)))
    op.add_column("payments", sa.Column("external_receipt", sa.JSON()))
    op.create_index(
        "uq_payment_external_request", "payments", ["external_request_key"], unique=True,
        postgresql_where=sa.text("external_request_key IS NOT NULL"),
        sqlite_where=sa.text("external_request_key IS NOT NULL"),
    )
    condition = sa.text("status = 'COMPLETED' AND external_receipt_key IS NOT NULL")
    op.create_index(
        "uq_payment_external_receipt",
        "payments",
        ["external_receipt_key"],
        unique=True,
        postgresql_where=condition,
        sqlite_where=condition,
    )
    if postgres:
        op.execute("""CREATE FUNCTION protect_external_payments() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF OLD.external_request_key IS NOT NULL THEN
                    IF TG_OP = 'UPDATE' AND OLD.status = 'COMPLETED' AND NEW.status = 'REVERSED'
                        AND (to_jsonb(NEW) - 'status') = (to_jsonb(OLD) - 'status') THEN
                        RETURN NEW;
                    END IF;
                    RAISE EXCEPTION 'External payment evidence is retained';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END; $$""")
        op.execute("""CREATE TRIGGER payments_external_retained BEFORE UPDATE OR DELETE ON payments
                      FOR EACH ROW EXECUTE FUNCTION protect_external_payments()""")
    else:
        unchanged = " AND ".join(
            f"NEW.{column['name']} IS OLD.{column['name']}"
            for column in sa.inspect(op.get_bind()).get_columns("payments")
            if column["name"] != "status"
        )
        op.execute(f"""CREATE TRIGGER payments_external_no_update BEFORE UPDATE ON payments
            WHEN OLD.external_request_key IS NOT NULL AND NOT (
                OLD.status = 'COMPLETED' AND NEW.status = 'REVERSED' AND {unchanged})
            BEGIN SELECT RAISE(ABORT, 'External payment evidence is retained'); END""")
        op.execute("""CREATE TRIGGER payments_external_no_delete BEFORE DELETE ON payments
            WHEN OLD.external_request_key IS NOT NULL
            BEGIN SELECT RAISE(ABORT, 'External payment evidence is retained'); END""")


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("""SELECT 1 FROM payments WHERE external_request_key IS NOT NULL
        UNION ALL SELECT 1 FROM filing_transactions
        WHERE event_type IN ('fee_payment_recorded', 'fee_payment_reversed') LIMIT 1""")
    ):
        raise RuntimeError("Cannot discard retained external payment credits or reversals")
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("DROP TRIGGER payments_external_retained ON payments")
        op.execute("DROP FUNCTION protect_external_payments()")
    else:
        op.execute("DROP TRIGGER payments_external_no_update")
        op.execute("DROP TRIGGER payments_external_no_delete")
    op.drop_index("uq_payment_external_receipt", table_name="payments")
    op.drop_index("uq_payment_external_request", table_name="payments")
    for column in ("external_receipt", "external_receipt_key", "external_request_key"):
        op.drop_column("payments", column)
    op.drop_column("filing_envelopes", "payment_version")
    # PostgreSQL keeps the unused enum label; no payment can use it without retained evidence.
