import sqlalchemy as sa

from alembic import op

revision = "d26e49b73c18"
down_revision = "b51d804a3e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("administration_version", sa.Integer(), nullable=False, server_default="0"),
    )
    connection = op.get_bind()
    roles = sa.table(
        "user_court_roles",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("court_id", sa.Integer()),
        sa.column("role", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    first_grants = sa.select(sa.func.min(roles.c.id)).group_by(
        roles.c.user_id,
        roles.c.court_id,
        roles.c.role,
    )
    audit = sa.table(
        "audit_log",
        sa.column("action", sa.String()),
        sa.column("entity_type", sa.String()),
        sa.column("entity_id", sa.Integer()),
        sa.column("details", sa.JSON()),
    )
    for row in connection.execute(
        sa.select(roles).where(roles.c.id.not_in(first_grants))
    ).mappings():
        connection.execute(
            audit.insert().values(
                action="identity.duplicate_role_removed",
                entity_type="user",
                entity_id=row["user_id"],
                details={
                    "court_id": row["court_id"],
                    "role": row["role"],
                    "former_id": row["id"],
                    "created_at": str(row["created_at"]),
                },
            )
        )
    connection.execute(roles.delete().where(roles.c.id.not_in(first_grants)))
    op.create_index(
        "uq_user_court_role", "user_court_roles", ["user_id", "court_id", "role"], unique=True
    )
    op.drop_index("ix_user_court_roles_user_id", "user_court_roles")
    op.create_index("ix_audit_entity_history", "audit_log", ["entity_type", "entity_id", "id"])
    if connection.dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_audit_log() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$""")
        op.execute("""CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION protect_audit_log()""")
    else:
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER audit_log_no_{operation.lower()}
                BEFORE {operation} ON audit_log
                BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END""")


def downgrade() -> None:
    raise RuntimeError("Retained identity audit records cannot be downgraded automatically")
