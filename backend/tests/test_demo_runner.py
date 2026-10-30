import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest

import run_demo


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.setattr(run_demo, "FRONTEND_DIR", tmp_path)
    monkeypatch.setattr(run_demo, "check_ports", lambda: None)
    monkeypatch.setattr(run_demo.shutil, "which", lambda command: command)
    stop = Mock()
    monkeypatch.setattr(run_demo, "stop_process", stop)
    return stop


def test_failed_install_does_not_seed_or_launch_servers(runner, monkeypatch, capsys):
    failed_install = Mock()
    failed_install.wait.return_value = 1
    start = Mock(return_value=failed_install)
    monkeypatch.setattr(run_demo, "start_process", start)

    assert run_demo.main() == 1
    assert start.call_count == 1
    assert start.call_args.args[0][-1] == "ci"
    output = capsys.readouterr()
    assert "installation failed" in output.err
    assert "MUEFS is ready" not in output.out
    runner.assert_called_once_with(failed_install)


@pytest.mark.parametrize("failure", ["frontend_start", "readiness", "frontend_exit"])
def test_frontend_failure_cleans_up_backend(runner, monkeypatch, capsys, failure):
    vite = run_demo.FRONTEND_DIR / "node_modules" / "vite" / "bin" / "vite.js"
    vite.parent.mkdir(parents=True)
    vite.touch()
    seed = Mock()
    seed.wait.return_value = 0
    backend = Mock()
    backend.poll.return_value = None
    frontend = Mock()
    frontend.poll.return_value = 1
    start = Mock(side_effect=[
        seed, backend,
        OSError("frontend start failed") if failure == "frontend_start" else frontend,
    ])
    monkeypatch.setattr(run_demo, "start_process", start)
    readiness = Mock(
        side_effect=[None, RuntimeError("not ready")] if failure == "readiness" else None,
    )
    monkeypatch.setattr(run_demo, "wait_until_ready", readiness)

    assert run_demo.main() == 1
    assert backend in [call.args[0] for call in runner.call_args_list]
    if failure != "frontend_start":
        assert runner.call_args_list[0].args == (frontend,)
    output = capsys.readouterr()
    if failure == "frontend_exit":
        assert "Frontend exited unexpectedly" in output.err
    else:
        assert "MUEFS is ready" not in output.out


def test_environment_keeps_backend_and_browser_demo_auth_in_sync(monkeypatch):
    monkeypatch.setenv("DEMO_MODE_SECRET", "saved-hosted-demo-secret")
    monkeypatch.setenv("EMAIL_DELIVERY_ENABLED", "true")
    original = dict(os.environ)
    env = run_demo.demo_environment()
    assert env["DEMO_MODE_SECRET"] == env["VITE_DEMO_MODE_SECRET"] == ""
    assert env["EMAIL_DELIVERY_ENABLED"] == env["SERVICE_DELIVERY_ENABLED"] == "false"
    assert dict(os.environ) == original


def test_readiness_retries_503_and_ignores_external_proxy(monkeypatch):
    attempts = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            attempts.append(self.path)
            self.send_response(200 if len(attempts) > 1 else 503)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    try:
        run_demo.wait_until_ready(f"http://127.0.0.1:{server.server_port}/ready", [])
        assert attempts == ["/ready", "/ready"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_readiness_failure_has_a_deadline(monkeypatch):
    monkeypatch.setattr(run_demo, "STARTUP_TIMEOUT", 0.01)
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        with pytest.raises(RuntimeError, match="Timed out waiting"):
            run_demo.wait_until_ready(f"http://127.0.0.1:{unavailable.getsockname()[1]}", [])


def refuses_connections(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            return False
    except ConnectionRefusedError:
        return True
    except TimeoutError:
        return False


def test_stop_process_closes_a_real_descendant_listener(tmp_path):
    port_file = tmp_path / "child-port.txt"
    child_code = """
import os, socket, sys, time
from pathlib import Path
listener = socket.socket()
listener.bind(("127.0.0.1", 0))
listener.listen()
# Publish atomically: the parent must never read a created but unwritten file.
Path(sys.argv[1] + ".tmp").write_text(str(listener.getsockname()[1]))
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
# Drain probes: on Windows a full backlog refuses connections like a closed port.
deadline = time.monotonic() + 60
while (remaining := deadline - time.monotonic()) > 0:
    listener.settimeout(remaining)
    try:
        listener.accept()[0].close()
    except TimeoutError:
        break
"""
    parent_code = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}, sys.argv[1]]); "
        "time.sleep(60)"
    )
    process = run_demo.start_process(
        [sys.executable, "-c", parent_code, str(port_file)], Path.cwd(), dict(os.environ),
    )
    try:
        deadline = time.monotonic() + 10
        while not port_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert port_file.exists(), "The test's child process did not start"
        port = int(port_file.read_text())
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        run_demo.stop_process(process)
        assert process.poll() is not None
        deadline = time.monotonic() + 15
        while not refuses_connections(port):
            assert time.monotonic() < deadline, f"A descendant still listens on port {port}"
            time.sleep(0.1)
    finally:
        if process.poll() is None:
            run_demo.stop_process(process)


def test_an_ipv6_localhost_listener_counts_as_occupied():
    try:
        listener = socket.socket(socket.AF_INET6)
        listener.bind(("::1", 0))
    except OSError:
        pytest.skip("IPv6 loopback is unavailable")
    with listener:
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(RuntimeError, match=f"Port {port} is unavailable"):
            run_demo.check_ports((port,))


def test_occupied_port_fails_before_any_database_or_child_work(monkeypatch, capsys):
    monkeypatch.setattr(
        run_demo, "check_ports", Mock(side_effect=RuntimeError("Port 8000 is busy")),
    )
    start = Mock()
    monkeypatch.setattr(run_demo, "start_process", start)
    assert run_demo.main() == 1
    start.assert_not_called()
    assert "Port 8000 is busy" in capsys.readouterr().err
