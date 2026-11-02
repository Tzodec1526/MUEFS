from alembic import op

revision = "e6b3f0a72c95"
down_revision = "c39f64dbea05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS deliverystatus")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TYPE deliverystatus AS ENUM ('PENDING', 'SENT', 'DELIVERED', 'FAILED')"
        )
