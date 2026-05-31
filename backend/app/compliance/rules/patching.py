"""Patch and supported-platform controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_LAST_PATCHED_AT,
    ATTR_OS_SUPPORTED,
    age_days,
    coerce_bool,
    failed,
    get_attr,
    not_applicable,
    passed,
)
from app.models.enums import Severity

if TYPE_CHECKING:
    from app.models.asset import Asset

# Maximum tolerated days since the last patch before the asset is non-compliant.
MAX_PATCH_AGE_DAYS = 30


@rule(
    id="patch-age",
    title="Patched within the last 30 days",
    framework="CIS Benchmark",
    control="SI-2 (also NIST SP 800-53)",
    severity=Severity.high,
    description="Security patches must be applied within 30 days to limit exposure to known CVEs.",
    remediation="Run the patch cycle; ensure the asset reports a last_patched_at within 30 days.",
)
def patch_age(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_LAST_PATCHED_AT)
    if raw is None:
        return not_applicable(reason="last_patched_at attribute not reported")
    days = age_days(raw)
    if days is None:
        return not_applicable(reason="last_patched_at value unparsable", observed=raw)
    rounded = round(days, 1)
    if days < MAX_PATCH_AGE_DAYS:
        return passed(patch_age_days=rounded, threshold_days=MAX_PATCH_AGE_DAYS)
    return failed(patch_age_days=rounded, threshold_days=MAX_PATCH_AGE_DAYS)


@rule(
    id="os-supported",
    title="Operating system is vendor-supported (not EOL)",
    framework="NIST SP 800-53",
    control="SI-2",
    severity=Severity.critical,
    description="End-of-life operating systems receive no security updates and must be retired or upgraded.",
    remediation="Upgrade to a supported OS release or decommission the asset.",
)
def os_supported(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_OS_SUPPORTED)
    if raw is None:
        return not_applicable(reason="os_supported attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="os_supported value uninterpretable", observed=raw)
    if value:
        return passed(os_supported=True, expected=True)
    return failed(os_supported=False, expected=True)
