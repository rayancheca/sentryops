"""Synthetic health-check execution (HTTP + TCP).

The probes here are the lowest layer of Pillar 3: they take a configured
:class:`~app.models.observability.HealthCheck` and produce a
:class:`CheckOutcome`. Nothing in this module touches the database — the worker
and the API record the outcome separately via the observability service.

Contract (depended on by the worker vertical):
    - ``run_check(check)`` is the async dispatcher (http/tcp).
    - ``run_check_sync(check)`` is the ``asyncio.run`` wrapper used by the worker
      and the synchronous "run now" API endpoint.
    - Neither ever raises: a probe failure is reported as a DOWN
      :class:`CheckOutcome` carrying the error string.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.models.enums import CheckStatus, CheckType
from app.models.observability import HealthCheck

# Hard ceiling so a probe never blocks the worker/loop indefinitely, regardless
# of a check's configured latency budget.
_MAX_PROBE_TIMEOUT_SECONDS: float = 30.0
# Default TCP port when a check has none configured and the target lacks one.
_DEFAULT_TCP_PORT: int = 80


@dataclass(slots=True)
class CheckOutcome:
    """The result of probing a single health check at one point in time."""

    status: CheckStatus
    latency_ms: float | None
    status_code: int | None
    error: str | None


def _timeout_seconds(check: HealthCheck) -> float:
    """Probe timeout: the latency budget plus headroom, capped to a hard ceiling."""
    budget_seconds = max(check.latency_budget_ms, 0) / 1000.0
    # Give the probe a little slack beyond the budget so we can distinguish
    # "slow but reachable" (DOWN due to budget) from "never connected".
    return min(budget_seconds + 5.0, _MAX_PROBE_TIMEOUT_SECONDS)


async def _run_http_check(check: HealthCheck) -> CheckOutcome:
    """Probe an HTTP target, honoring method, expected status, and latency budget."""
    timeout = _timeout_seconds(check)
    method = (check.method or "GET").upper()
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(method, check.target)
    except httpx.HTTPError as exc:
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=None,
            status_code=None,
            error=f"request failed: {exc.__class__.__name__}",
        )

    latency_ms = (time.perf_counter() - start) * 1000.0
    status_code = response.status_code

    if status_code != check.expected_status:
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=latency_ms,
            status_code=status_code,
            error=f"unexpected status {status_code} (expected {check.expected_status})",
        )
    if latency_ms > check.latency_budget_ms:
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=latency_ms,
            status_code=status_code,
            error=f"latency {latency_ms:.0f}ms over budget {check.latency_budget_ms}ms",
        )
    return CheckOutcome(
        status=CheckStatus.up,
        latency_ms=latency_ms,
        status_code=status_code,
        error=None,
    )


def _tcp_host_port(check: HealthCheck) -> tuple[str, int]:
    """Resolve (host, port) for a TCP check from its target/port fields.

    ``target`` may be a bare host ("db.internal"), a host:port pair, or a URL.
    An explicit ``check.port`` always wins.
    """
    target = check.target.strip()
    host = target
    port: int | None = check.port

    if "://" in target:
        parsed = urlparse(target)
        host = parsed.hostname or target
        if port is None and parsed.port is not None:
            port = parsed.port
    elif ":" in target and target.count(":") == 1:
        # Plain "host:port"; split only on a single colon to avoid mangling IPv6.
        host_part, _, port_part = target.partition(":")
        host = host_part
        if port is None and port_part.isdigit():
            port = int(port_part)

    return host, port if port is not None else _DEFAULT_TCP_PORT


async def _run_tcp_check(check: HealthCheck) -> CheckOutcome:
    """Probe a TCP target by opening (and immediately closing) a connection."""
    host, port = _tcp_host_port(check)
    timeout = _timeout_seconds(check)
    start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (TimeoutError, OSError) as exc:
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=None,
            status_code=None,
            error=f"connect failed: {exc.__class__.__name__}",
        )

    latency_ms = (time.perf_counter() - start) * 1000.0
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        # The connection succeeded; a failure tearing it down is not a probe failure.
        pass

    if latency_ms > check.latency_budget_ms:
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=latency_ms,
            status_code=None,
            error=f"latency {latency_ms:.0f}ms over budget {check.latency_budget_ms}ms",
        )
    return CheckOutcome(
        status=CheckStatus.up,
        latency_ms=latency_ms,
        status_code=None,
        error=None,
    )


async def run_check(check: HealthCheck) -> CheckOutcome:
    """Dispatch to the right probe for ``check``; never raises."""
    try:
        if check.check_type == CheckType.http:
            return await _run_http_check(check)
        if check.check_type == CheckType.tcp:
            return await _run_tcp_check(check)
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=None,
            status_code=None,
            error=f"unsupported check type: {check.check_type}",
        )
    except Exception as exc:  # noqa: BLE001 - probes must never propagate.
        return CheckOutcome(
            status=CheckStatus.down,
            latency_ms=None,
            status_code=None,
            error=f"probe error: {exc.__class__.__name__}",
        )


def run_check_sync(check: HealthCheck) -> CheckOutcome:
    """Synchronous wrapper used by the worker and the 'run now' API endpoint."""
    return asyncio.run(run_check(check))
