"""Run the MUEFS application in demo mode with SQLite.

Usage: python run_demo.py
"""

import os
import signal
import subprocess
import sys

# Force SQLite for demo (no PostgreSQL needed)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./demo.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///./demo.db"
os.environ["DEBUG"] = "true"
os.environ["ALLOW_DEMO_MODE"] = "true"
os.environ["PAYMENTS_ARE_SIMULATED"] = "true"
os.environ["EXTERNAL_PAYMENTS_ENABLED"] = "false"
os.environ["EMAIL_DELIVERY_ENABLED"] = "false"
os.environ["SERVICE_DELIVERY_ENABLED"] = "false"
os.environ["ALLOW_PUBLIC_REGISTRATION"] = "true"
os.environ["RATE_LIMIT_BACKEND"] = "memory"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,http://localhost:5173,http://0.0.0.0:3000"
os.environ["S3_ENDPOINT_URL"] = "http://localhost:9000"  # Won't connect but won't crash
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("  Michigan Unified E-Filing System - Demo Mode")
    print("=" * 60)
    print()

    # Setup database
    from app.seed_data import seed_database
    seed_database()

    # Start backend
    print("\nStarting backend on http://localhost:8000 ...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload"],
        env=os.environ.copy(),
    )

    # Install frontend deps if needed
    frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
    # On Windows, npm is npm.cmd.
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("\nInstalling frontend dependencies (first time only)...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, capture_output=True)

    # Start frontend
    print("Starting frontend on http://localhost:3000 ...")
    fe_env = os.environ.copy()
    fe_env["VITE_ALLOW_DEMO_MODE"] = "true"
    fe_env["VITE_API_URL"] = ""
    fe_env["VITE_KEYCLOAK_URL"] = ""
    fe_env["VITE_DEMO_MODE_SECRET"] = ""
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
        env=fe_env,
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
