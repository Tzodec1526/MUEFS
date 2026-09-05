"""Retain court calendar revisions and distinguish filing dates from receipt instants."""

import sqlalchemy as sa

from alembic import op

revision = "a8b712e43c90"
down_revision = "f38d104ac927"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "court_calendars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("court_id", sa.Integer(), sa.ForeignKey("courts.id"), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_through", sa.Date(), nullable=False),
        sa.Column("closed_dates", sa.JSON(), nullable=False),
        sa.Column("authority_reference", sa.String(1000), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_calendar_court_coverage", "court_calendars", ["court_id", "valid_through", "id"]
    )
    op.add_column("filing_envelopes", sa.Column("filing_date", sa.Date()))
    op.add_column("filing_envelopes", sa.Column("filing_date_basis", sa.JSON()))
    op.add_column("cases", sa.Column("filing_date", sa.Date()))
    # No calendar or filing date is invented for historical cases or submissions.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_court_calendars() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'court_calendars is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER court_calendars_append_only BEFORE UPDATE OR DELETE
            ON court_calendars FOR EACH ROW EXECUTE FUNCTION protect_court_calendars()""")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER court_calendars_no_{operation.lower()}
                BEFORE {operation} ON court_calendars
                BEGIN SELECT RAISE(ABORT, 'court_calendars is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError(
        "Retained calendars and filing dates cannot be downgraded automatically. "
        "Use the court's verified backup and recovery procedure."
    )
