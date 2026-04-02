"""Run the MUEFS application in demo mode with SQLite.

Usage: python run_demo.py
"""

import os
import sys
import subprocess
import time
import signal

# Force SQLite for demo (no PostgreSQL needed)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./demo.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///./demo.db"
os.environ["DEBUG"] = "true"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"
os.environ["S3_ENDPOINT_URL"] = "http://localhost:9000"  # Won't connect but won't crash
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Patch the database module to use SQLite
def setup_demo_db():
    """Create tables and seed data using SQLite."""
    from sqlalchemy import create_engine, JSON
    from sqlalchemy.orm import Session
    from app.database import Base

    # Import all models to register them
    import app.models  # noqa

    engine = create_engine("sqlite:///./demo.db", echo=False)
    Base.metadata.create_all(engine)
    print("Demo database created.")

    # Seed data
    from app.models.court import Court
    with Session(engine) as session:
        if session.query(Court).first():
            print("Database already seeded.")
            return

    # Run seed script
    from app.seed_data import seed_database
    try:
        seed_database()
        print("Database seeded with Michigan courts.")
    except Exception as e:
        print(f"Seed warning (non-fatal): {e}")
        # Manual minimal seed for demo
        with Session(engine) as session:
            from app.models.user import User, UserType
            from app.models.court import Court, CourtType, CaseType, CaseCategory

            # Demo users
            session.add(User(
                email="attorney@demo.muefs.gov",
                first_name="Jane", last_name="Doe",
                user_type=UserType.ATTORNEY, bar_number="P12345",
                firm_name="Doe & Associates PLLC",
            ))
            session.add(User(
                email="clerk@demo.muefs.gov",
                first_name="Robert", last_name="Johnson",
                user_type=UserType.CLERK,
            ))

            # A few courts
            for name, county, city in [
                ("3rd Circuit Court", "Wayne", "Detroit"),
                ("6th Circuit Court", "Oakland", "Pontiac"),
                ("17th Circuit Court", "Kent", "Grand Rapids"),
                ("36th District Court", "Wayne", "Detroit"),
            ]:
                court = Court(name=name, county=county, city=city,
                              court_type=CourtType.CIRCUIT, state="MI",
                              cms_type="JIS", is_efiling_enabled=True)
                session.add(court)
                session.flush()
                session.add(CaseType(court_id=court.id, code="CIV-GEN",
                    name="Civil - General", category=CaseCategory.CIVIL,
                    filing_fee_cents=17500))
                session.add(CaseType(court_id=court.id, code="FAM-DIV",
                    name="Divorce/Dissolution", category=CaseCategory.FAMILY,
                    filing_fee_cents=17500))
            session.commit()
            print("Minimal demo data seeded.")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("  Michigan Unified E-Filing System - Demo Mode")
    print("=" * 60)
    print()

    # Setup database
    sys.path.insert(0, ".")
    setup_demo_db()

    # Start backend
    print("\nStarting backend on http://localhost:8000 ...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        env=os.environ.copy(),
    )

    # Install frontend deps if needed
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
    # On Windows, npm is npm.cmd; use shell=True for cross-platform compatibility
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("\nInstalling frontend dependencies (first time only)...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, capture_output=True)

    # Start frontend
    print("Starting frontend on http://localhost:3000 ...")
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
        env=os.environ.copy(),
    )

    print()
    print("=" * 60)
    print("  MUEFS is running!")
    print()
    print("  Frontend:  http://localhost:3000")
    print("  API:       http://localhost:8000")
    print("  API Docs:  http://localhost:8000/docs")
    print()
    print("  Press Ctrl+C to stop all services")
    print("=" * 60)

    def shutdown(sig, frame):
        print("\nShutting down...")
        backend.terminate()
        frontend.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        backend.wait()
    except KeyboardInterrupt:
        shutdown(None, None)
