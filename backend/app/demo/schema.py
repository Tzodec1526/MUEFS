"""Upgrade local/demo SQLite databases without resetting filings or stored documents."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, inspect

from alembic import command
from app.database import Base


def prepare_demo_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        raise ValueError("Demo schema setup only supports SQLite; use Alembic for production")
    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        inspector = inspect(connection)
        if not inspector.has_table("courts"):
            Base.metadata.create_all(connection)
            command.stamp(config, "head")
            return
        if not inspector.has_table("alembic_version"):
            # Earlier demos used create_all without migration tracking. Adopt the
            # last known schema, then apply the same retained-history migration.
            columns = {c["name"] for c in inspector.get_columns("filing_envelopes")}
            revision = "c4f8e2a91b0d" if "cms_filing_id" in columns else "baec3dbedabf"
            command.stamp(config, revision)
        command.upgrade(config, "head")
