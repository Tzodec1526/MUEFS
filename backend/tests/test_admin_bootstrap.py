"""Exercise the operator entry point against a fresh, migrated database."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.demo.schema import prepare_demo_schema


def test_first_admin_bootstrap_is_retained_and_cannot_be_replayed(tmp_path):
    database = tmp_path / "first-admin.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        prepare_demo_schema(engine)
        command = [
            sys.executable,
            "-m",
            "app.admin_bootstrap",
            "--email",
            "operator@example.com",
            "--first-name",
            "Initial",
            "--last-name",
            "Operator",
            "--subject",
            "trusted-subject",
            "--reason",
            "Deployment authorization ADM-001",
        ]
        environment = {
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
            "DEBUG": "false",
            "ALLOW_DEMO_MODE": "false",
            "DEMO_ISOLATED_SESSIONS": "false",
        }
        first = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert first.returncode == 0, first.stderr
        again = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert again.returncode != 0 and "already exists" in again.stderr
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert connection.scalar(text("SELECT keycloak_id FROM users")) == "trusted-subject"
            assert connection.scalar(text("SELECT verified_email FROM users")) is None
            assert connection.scalar(text("SELECT action FROM audit_log")) == "identity.bootstrap"
            assert connection.scalar(text("SELECT user_id FROM audit_log")) is None
    finally:
        engine.dispose()
