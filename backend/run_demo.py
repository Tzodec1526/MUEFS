import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
STARTUP_TIMEOUT = 60


def demo_environment() -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": "sqlite+aiosqlite:///./demo.db",
        "DEBUG": "true",
        "ALLOW_DEMO_MODE": "true",
        "DEMO_MODE_SECRET": "",
        "DEMO_ISOLATED_SESSIONS": "false",
        "ENABLE_API_DOCS": "true",
        "PAYMENTS_ARE_SIMULATED": "true",
        "EXTERNAL_PAYMENTS_ENABLED": "false",
        "EMAIL_DELIVERY_ENABLED": "false",
        "SERVICE_DELIVERY_ENABLED": "false",
        "ALLOW_PUBLIC_REGISTRATION": "true",
        "RATE_LIMIT_BACKEND": "memory",
        "ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "VITE_ALLOW_DEMO_MODE": "true",
        "VITE_API_URL": "",
        "VITE_KEYCLOAK_URL": "",
        "VITE_DEMO_MODE_SECRET": "",
        "PYTHONUNBUFFERED": "1",
    }


def check_ports(ports: tuple[int, ...] = (8000, 3000)) -> None:
    for port in ports:
        unavailable = RuntimeError(
            f"Port {port} is unavailable. Stop the service using it and try again."
        )
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise unavailable from exc
        for family, kind, protocol, _, address in socket.getaddrinfo(
            "localhost", port, type=socket.SOCK_STREAM,
        ):
            with socket.socket(family, kind, protocol) as client:
                client.settimeout(0.5)
                if client.connect_ex(address) == 0:
                    raise unavailable


def start_process(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command, cwd=cwd, env=env,
        start_new_session=sys.platform != "win32",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def stop_process(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def check_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for name, process in processes:
        code = process.poll()
        if code is not None:
            raise RuntimeError(
                f"{name} exited unexpectedly (exit code {code}). See its output above."
            )


def wait_until_ready(url: str, processes: list[tuple[str, subprocess.Popen]]) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    client = build_opener(ProxyHandler({}))
    while time.monotonic() < deadline:
        check_processes(processes)
        try:
            with client.open(url, timeout=1) as response:
                if response.status == 200:
                    check_processes(processes)
                    return
        except HTTPError as exc:
            exc.close()
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for {url}. See the service output above.")


def main() -> int:
    processes: list[tuple[str, subprocess.Popen]] = []
    previous_handlers = {}

    def shutdown(_signum, _frame):
        raise KeyboardInterrupt

    try:
        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, "SIGHUP"):
            signals.append(signal.SIGHUP)
        for signum in signals:
            previous_handlers[signum] = signal.signal(signum, shutdown)
        print("Michigan Unified E-Filing System - Local Demo", flush=True)
        check_ports()
        node = shutil.which("node")
        npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
        if not node or not npm:
            raise RuntimeError(
                "Node.js and npm are required. Install Node.js 22.12+ and try again."
            )
        env = demo_environment()
        vite = FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
        if not vite.is_file():
            print("Installing frontend dependencies from package-lock.json...", flush=True)
            install = start_process([npm, "ci"], FRONTEND_DIR, env)
            processes.append(("Dependency installation", install))
            if install.wait() != 0:
                raise RuntimeError(
                    "Frontend dependency installation failed. See npm's output above."
                )
            processes.remove(("Dependency installation", install))

        print("Preparing the demo database...", flush=True)
        seed = start_process([sys.executable, "-m", "app.seed_data"], BACKEND_DIR, env)
        processes.append(("Database setup", seed))
        if seed.wait() != 0:
            raise RuntimeError("Demo database setup failed. See its output above.")
        processes.remove(("Database setup", seed))

        print("Starting backend on http://localhost:8000 ...", flush=True)
        backend = start_process(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", "8000"], BACKEND_DIR, env,
        )
        processes.append(("Backend", backend))
        wait_until_ready("http://127.0.0.1:8000/ready", processes)

        print("Starting frontend on http://localhost:3000 ...", flush=True)
        frontend = start_process(
            [node, str(vite), "--host", "127.0.0.1", "--port", "3000", "--strictPort"],
            FRONTEND_DIR, env,
        )
        processes.append(("Frontend", frontend))
        wait_until_ready("http://127.0.0.1:3000", processes)
        print(
            "\nMUEFS is ready!\n\n"
            "  Frontend: http://localhost:3000\n"
            "  API:      http://localhost:8000\n"
            "  API Docs: http://localhost:8000/docs\n\n"
            "Press Ctrl+C to stop all services.", flush=True,
        )
        while True:
            check_processes(processes)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"\nDemo could not run: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            for _, process in reversed(processes):
                stop_process(process)
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


if __name__ == "__main__":
    sys.exit(main())
