"""Drop the PostgreSQL enum type that notice delivery status no longer uses."""

from alembic import op

revision = "e6b3f0a72c95"
down_revision = "c39f64dbea05"
branch_labels = None
depends_on = None

# b51d804a3e62 changed notifications.delivery_status to a string but left the type behind.
# The models do not own it, so a schema reset kept it and the baseline could not recreate it.


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS deliverystatus")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TYPE deliverystatus AS ENUM ('PENDING', 'SENT', 'DELIVERED', 'FAILED')"
        )
