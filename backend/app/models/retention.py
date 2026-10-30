from sqlalchemy import DDL, FromClause, Table, event


def append_only(table: FromClause) -> None:
    assert isinstance(table, Table)
    name = table.name
    for operation in ("UPDATE", "DELETE"):
        event.listen(
            table,
            "after_create",
            DDL(f"""
            CREATE TRIGGER {name}_no_{operation.lower()} BEFORE {operation} ON {name}
            BEGIN SELECT RAISE(ABORT, '{name} is append-only'); END
        """).execute_if(dialect="sqlite"),
        )
    event.listen(
        table,
        "after_create",
        DDL(f"""
        CREATE FUNCTION protect_{name}() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION '{name} is append-only'; END; $$
    """).execute_if(dialect="postgresql"),
    )
    event.listen(
        table,
        "after_create",
        DDL(f"""
        CREATE TRIGGER {name}_append_only BEFORE UPDATE OR DELETE ON {name}
        FOR EACH ROW EXECUTE FUNCTION protect_{name}()
    """).execute_if(dialect="postgresql"),
    )
    event.listen(
        table,
        "after_drop",
        DDL(f"DROP FUNCTION IF EXISTS protect_{name}()").execute_if(dialect="postgresql"),
    )
