"""Network and boundary-protection controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_FIREWALL_ENABLED,
    ATTR_OPEN_PORTS,
    ATTR_TLS_CERT_EXPIRES_AT,
    HIGH_RISK_PORTS,
    coerce_bool,
    days_until,
    failed,
    get_attr,
    not_applicable,
    passed,
)
from app.models.enums import Severity

if TYPE_CHECKING:
    from app.models.asset import Asset

# Minimum days of validity a TLS certificate must retain to be compliant.
MIN_TLS_CERT_DAYS = 30


@rule(
    id="firewall-enabled",
    title="Host firewall enabled",
    framework="CIS Benchmark",
    control="SC-7 (also NIST SP 800-53)",
    severity=Severity.high,
    description="A host-based firewall must be active to control inbound and outbound traffic.",
    remediation="Enable the host firewall (ufw, firewalld, Windows Defender Firewall) with a default-deny inbound policy.",
)
def firewall_enabled(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_FIREWALL_ENABLED)
    if raw is None:
        return not_applicable(reason="firewall_enabled attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="firewall_enabled value uninterpretable", observed=raw)
    if value:
        return passed(firewall_enabled=True, expected=True)
    return failed(firewall_enabled=False, expected=True)


@rule(
    id="no-high-risk-open-ports",
    title="No high-risk ports exposed",
    framework="CIS Benchmark",
    control="SC-7 (also NIST SP 800-53)",
    severity=Severity.high,
    description="Legacy/plaintext management ports (telnet, SMB, RDP, FTP) must not be exposed.",
    remediation="Close or firewall ports 21, 23, 445, 2323, and 3389; use SSH/VPN for remote management.",
)
def no_high_risk_open_ports(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_OPEN_PORTS)
    if raw is None:
        return not_applicable(reason="open_ports attribute not reported")
    if not isinstance(raw, (list, tuple)):
        return not_applicable(reason="open_ports is not a list", observed=raw)
    ports: set[int] = set()
    for item in raw:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ports.add(item)
        elif isinstance(item, str) and item.strip().isdigit():
            ports.add(int(item.strip()))
    offending = sorted(ports & HIGH_RISK_PORTS)
    if offending:
        return failed(
            open_high_risk_ports=offending,
            high_risk_ports=sorted(HIGH_RISK_PORTS),
        )
    return passed(open_high_risk_ports=[], high_risk_ports=sorted(HIGH_RISK_PORTS))


@rule(
    id="tls-cert-expiry",
    title="TLS certificate valid for at least 30 more days",
    framework="NIST SP 800-53",
    control="SC-12",
    severity=Severity.high,
    description="An expiring TLS certificate risks an outage and weakens transport security.",
    remediation="Renew the TLS certificate so it has more than 30 days of validity remaining.",
)
def tls_cert_expiry(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_TLS_CERT_EXPIRES_AT)
    if raw is None:
        return not_applicable(reason="tls_cert_expires_at attribute not reported")
    remaining = days_until(raw)
    if remaining is None:
        return not_applicable(reason="tls_cert_expires_at value unparsable", observed=raw)
    rounded = round(remaining, 1)
    if remaining >= MIN_TLS_CERT_DAYS:
        return passed(days_until_expiry=rounded, threshold_days=MIN_TLS_CERT_DAYS)
    return failed(days_until_expiry=rounded, threshold_days=MIN_TLS_CERT_DAYS)
