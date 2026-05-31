"""Identity, authentication, and ownership controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_HAS_DEFAULT_CREDENTIALS,
    ATTR_PASSWORD_MAX_AGE_DAYS,
    coerce_bool,
    failed,
    get_attr,
    not_applicable,
    passed,
)
from app.models.enums import Severity

if TYPE_CHECKING:
    from app.models.asset import Asset

# Maximum acceptable password rotation interval, in days.
MAX_PASSWORD_AGE_DAYS = 90


@rule(
    id="owner-mfa",
    title="Asset owner has MFA enabled",
    framework="NIST SP 800-53",
    control="IA-2",
    severity=Severity.critical,
    description="The accountable owner of an asset must protect their account with multi-factor authentication.",
    remediation="Enrol the asset owner in MFA, or reassign ownership to an MFA-protected account.",
)
def owner_mfa(asset: Asset) -> RuleEvaluation:
    owner = asset.owner
    if owner is None:
        # No owner -> cannot assess the owner's MFA. Orphan ownership is caught
        # by the dedicated has-owner rule, not penalised twice here.
        return not_applicable(reason="asset has no assigned owner")
    if owner.mfa_enabled:
        return passed(owner_mfa_enabled=True, owner_id=str(owner.id))
    return failed(owner_mfa_enabled=False, owner_id=str(owner.id))


@rule(
    id="no-default-credentials",
    title="No default or vendor-shipped credentials",
    framework="NIST SP 800-53",
    control="IA-5",
    severity=Severity.critical,
    description="Default credentials are publicly known and must be removed or rotated before deployment.",
    remediation="Delete or change every default account; verify the asset reports no default credentials.",
)
def no_default_credentials(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_HAS_DEFAULT_CREDENTIALS)
    if raw is None:
        return not_applicable(reason="has_default_credentials attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="has_default_credentials value uninterpretable", observed=raw)
    if value:
        return failed(has_default_credentials=True, expected=False)
    return passed(has_default_credentials=False, expected=False)


@rule(
    id="password-max-age",
    title="Password rotation at most every 90 days",
    framework="NIST SP 800-53",
    control="IA-5",
    severity=Severity.medium,
    description="Local credential rotation policy must require a change at least every 90 days.",
    remediation="Set the maximum password age policy to 90 days or fewer.",
)
def password_max_age(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_PASSWORD_MAX_AGE_DAYS)
    if raw is None:
        return not_applicable(reason="password_max_age_days attribute not reported")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return not_applicable(reason="password_max_age_days not numeric", observed=raw)
    observed = int(raw)
    if observed <= MAX_PASSWORD_AGE_DAYS:
        return passed(password_max_age_days=observed, threshold_days=MAX_PASSWORD_AGE_DAYS)
    return failed(password_max_age_days=observed, threshold_days=MAX_PASSWORD_AGE_DAYS)


@rule(
    id="has-owner",
    title="Asset has an assigned owner (no orphans)",
    framework="NIST SP 800-53",
    control="CM-8",
    severity=Severity.low,
    description="Every asset in the inventory must have an accountable owner for lifecycle and security decisions.",
    remediation="Assign an owner to the asset in the CMDB.",
)
def has_owner(asset: Asset) -> RuleEvaluation:
    if asset.owner_id is not None:
        return passed(has_owner=True)
    return failed(has_owner=False)
