"""Encryption controls: data at rest and data in transit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_DISK_ENCRYPTED,
    ATTR_ENCRYPTION_IN_TRANSIT,
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
    id="disk-encryption",
    title="Full-disk encryption enabled",
    framework="NIST SP 800-53",
    control="SC-28 (also CIS Benchmark)",
    severity=Severity.high,
    description="Data at rest must be encrypted to protect against physical theft.",
    remediation="Enable full-disk encryption (BitLocker, LUKS, FileVault) and confirm the volume reports encrypted.",
)
def disk_encryption(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_DISK_ENCRYPTED)
    if raw is None:
        return not_applicable(reason="disk_encrypted attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="disk_encrypted value uninterpretable", observed=raw)
    if value:
        return passed(disk_encrypted=True, expected=True)
    return failed(disk_encrypted=False, expected=True)


@rule(
    id="encryption-in-transit",
    title="Encryption in transit enforced",
    framework="NIST SP 800-53",
    control="SC-8",
    severity=Severity.high,
    description="Data moving to/from the asset must use TLS or an equivalent encrypted channel.",
    remediation="Terminate plaintext protocols; enforce TLS 1.2+ on every listening service.",
)
def encryption_in_transit(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_ENCRYPTION_IN_TRANSIT)
    if raw is None:
        return not_applicable(reason="encryption_in_transit attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="encryption_in_transit value uninterpretable", observed=raw)
    if value:
        return passed(encryption_in_transit=True, expected=True)
    return failed(encryption_in_transit=False, expected=True)
