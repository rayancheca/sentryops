"""Endpoint malicious-code protection controls (EDR / antivirus)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_ANTIVIRUS_INSTALLED,
    ATTR_EDR_INSTALLED,
    coerce_bool,
    failed,
    get_attr,
    not_applicable,
    passed,
)
from app.models.enums import Severity

if TYPE_CHECKING:
    from app.models.asset import Asset


@rule(
    id="edr-present",
    title="Endpoint detection & response (EDR) agent installed",
    framework="NIST SP 800-53",
    control="SI-3",
    severity=Severity.high,
    description="An EDR agent must be present to detect and contain malicious activity.",
    remediation="Deploy the organisation's EDR agent and confirm it reports as installed and running.",
)
def edr_present(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_EDR_INSTALLED)
    if raw is None:
        return not_applicable(reason="edr_installed attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="edr_installed value uninterpretable", observed=raw)
    if value:
        return passed(edr_installed=True, expected=True)
    return failed(edr_installed=False, expected=True)


@rule(
    id="antivirus-present",
    title="Antivirus / anti-malware installed",
    framework="NIST SP 800-53",
    control="SI-3",
    severity=Severity.medium,
    description="Anti-malware protection must be installed to block known malicious code.",
    remediation="Install and enable an approved antivirus product with current signatures.",
)
def antivirus_present(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_ANTIVIRUS_INSTALLED)
    if raw is None:
        return not_applicable(reason="antivirus_installed attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="antivirus_installed value uninterpretable", observed=raw)
    if value:
        return passed(antivirus_installed=True, expected=True)
    return failed(antivirus_installed=False, expected=True)
