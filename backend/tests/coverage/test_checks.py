"""Behavioral tests for the synthetic probe layer (app/observability/checks.py).

Probes are exercised against real ephemeral servers bound to 127.0.0.1:
    * TCP — a listening socket on an OS-assigned port (UP) vs. a closed port (DOWN).
    * HTTP — a threaded ``http.server`` that can answer with an arbitrary status,
      plus a slow handler to drive the latency-budget DOWN path.

The contract under test: ``run_check`` / ``run_check_sync`` always return a
``CheckOutcome`` and never raise, regardless of the target's behavior.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.models.enums import CheckStatus, CheckType
from app.models.observability import HealthCheck
from app.observability.checks import CheckOutcome, run_check, run_check_sync

pytestmark = pytest.mark.unit


def _make_check(
    *,
    check_type: CheckType,
    target: str,
    expected_status: int = 200,
    latency_budget_ms: int = 5000,
    port: int | None = None,
    method: str = "GET",
) -> HealthCheck:
    """Build an unpersisted HealthCheck — probes never touch the DB."""
    return HealthCheck(
        service_id=None,
        name="probe",
        check_type=check_type,
        target=target,
        method=method,
        expected_status=expected_status,
        latency_budget_ms=latency_budget_ms,
        port=port,
        interval_seconds=60,
        enabled=True,
    )


# --------------------------------------------------------------------------- #
# TCP probes
# --------------------------------------------------------------------------- #


@pytest.fixture
def tcp_server() -> Iterator[int]:
    """A listening TCP socket on 127.0.0.1; yields the OS-assigned port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    port = sock.getsockname()[1]

    accepting = threading.Event()
    accepting.set()

    def _accept_loop() -> None:
        sock.settimeout(0.2)
        while accepting.is_set():
            try:
                conn, _addr = sock.accept()
            except (TimeoutError, OSError):
                continue
            conn.close()

    thread = threading.Thread(target=_accept_loop, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        accepting.clear()
        thread.join(timeout=2)
        sock.close()


def _free_port() -> int:
    """Reserve an ephemeral port, then release it so nothing is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_tcp_probe_up_against_listening_socket(tcp_server: int) -> None:
    # Arrange — explicit port wins over the (host-only) target.
    check = _make_check(check_type=CheckType.tcp, target="127.0.0.1", port=tcp_server)

    # Act
    outcome = run_check_sync(check)

    # Assert
    assert isinstance(outcome, CheckOutcome)
    assert outcome.status is CheckStatus.up
    assert outcome.latency_ms is not None
    assert outcome.error is None


def test_tcp_probe_down_against_closed_port() -> None:
    # Arrange — a port with nothing listening.
    check = _make_check(check_type=CheckType.tcp, target="127.0.0.1", port=_free_port())

    # Act
    outcome = run_check_sync(check)

    # Assert — a clean DOWN with a connect error, no exception.
    assert isinstance(outcome, CheckOutcome)
    assert outcome.status is CheckStatus.down
    assert outcome.error is not None
    assert "connect failed" in outcome.error


def test_tcp_probe_parses_host_port_from_target(tcp_server: int) -> None:
    # Arrange — port encoded in the "host:port" target, no explicit port field.
    check = _make_check(check_type=CheckType.tcp, target=f"127.0.0.1:{tcp_server}")

    # Act
    outcome = run_check_sync(check)

    # Assert
    assert outcome.status is CheckStatus.up


def test_tcp_probe_down_when_latency_over_budget(tcp_server: int) -> None:
    # Arrange — a zero/near-zero budget forces the over-budget DOWN branch even
    # though the connection itself succeeds.
    check = _make_check(
        check_type=CheckType.tcp, target="127.0.0.1", port=tcp_server, latency_budget_ms=0
    )

    # Act
    outcome = run_check_sync(check)

    # Assert — connected but reported DOWN due to the latency budget.
    assert outcome.status is CheckStatus.down
    assert outcome.latency_ms is not None
    assert "over budget" in (outcome.error or "")


# --------------------------------------------------------------------------- #
# HTTP probes
# --------------------------------------------------------------------------- #


class _Handler(BaseHTTPRequestHandler):
    status_code = 200
    delay_seconds = 0.0

    def do_GET(self) -> None:  # noqa: N802 — http.server dispatch name.
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.send_response(self.status_code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args: object) -> None:  # silence test-server noise.
        return


@pytest.fixture
def http_server() -> Iterator[ThreadingHTTPServer]:
    # Reset class state between tests (the handler class is shared).
    _Handler.status_code = 200
    _Handler.delay_seconds = 0.0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _http_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address[0], server.server_address[1]
    return f"http://{host}:{port}/health"


def test_http_probe_up_on_expected_status(http_server: ThreadingHTTPServer) -> None:
    # Arrange
    _Handler.status_code = 200
    check = _make_check(
        check_type=CheckType.http, target=_http_url(http_server), expected_status=200
    )

    # Act
    outcome = run_check_sync(check)

    # Assert
    assert outcome.status is CheckStatus.up
    assert outcome.status_code == 200
    assert outcome.latency_ms is not None
    assert outcome.error is None


def test_http_probe_down_on_unexpected_status(http_server: ThreadingHTTPServer) -> None:
    # Arrange — server returns 500 while the check expects 200.
    _Handler.status_code = 500
    check = _make_check(
        check_type=CheckType.http, target=_http_url(http_server), expected_status=200
    )

    # Act
    outcome = run_check_sync(check)

    # Assert
    assert outcome.status is CheckStatus.down
    assert outcome.status_code == 500
    assert "unexpected status 500" in (outcome.error or "")


def test_http_probe_down_when_latency_over_budget(http_server: ThreadingHTTPServer) -> None:
    # Arrange — the server stalls past a tiny latency budget.
    _Handler.status_code = 200
    _Handler.delay_seconds = 0.25
    check = _make_check(
        check_type=CheckType.http,
        target=_http_url(http_server),
        expected_status=200,
        latency_budget_ms=1,
    )

    # Act
    outcome = run_check_sync(check)

    # Assert — correct status code, but DOWN due to the budget.
    assert outcome.status is CheckStatus.down
    assert outcome.status_code == 200
    assert "over budget" in (outcome.error or "")


def test_http_probe_down_on_connection_failure() -> None:
    # Arrange — nothing is listening on this port.
    check = _make_check(
        check_type=CheckType.http,
        target=f"http://127.0.0.1:{_free_port()}/health",
        expected_status=200,
    )

    # Act
    outcome = run_check_sync(check)

    # Assert — a request failure surfaces as DOWN, never an exception.
    assert outcome.status is CheckStatus.down
    assert outcome.status_code is None
    assert "request failed" in (outcome.error or "")


# --------------------------------------------------------------------------- #
# Dispatcher contract
# --------------------------------------------------------------------------- #


async def test_run_check_async_returns_outcome_for_tcp(tcp_server: int) -> None:
    # Arrange
    check = _make_check(check_type=CheckType.tcp, target="127.0.0.1", port=tcp_server)

    # Act — the async dispatcher path.
    outcome = await run_check(check)

    # Assert
    assert isinstance(outcome, CheckOutcome)
    assert outcome.status is CheckStatus.up
