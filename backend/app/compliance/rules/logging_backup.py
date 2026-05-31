"""Audit-logging and backup/recovery controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_LAST_BACKUP_AT,
    ATTR_LOG_RETENTION_DAYS,
    ATTR_LOGGING_ENABLED,
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

# Maximum tolerated days since the last successful backup.
MAX_BACKUP_AGE_DAYS = 7
# Minimum audit-log retention window, in days.
MIN_LOG_RETENTION_DAYS = 30


@rule(
    id="logging-enabled",
    title="Audit logging enabled",
    framework="NIST SP 800-53",
    control="AU-2",
    severity=Severity.medium,
    description="Security-relevant events must be logged to support detection and forensics.",
    remediation="Enable audit logging and forward events to the central log store.",
)
def logging_enabled(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_LOGGING_ENABLED)
    if raw is None:
        return not_applicable(reason="logging_enabled attribute not reported")
    value = coerce_bool(raw)
    if value is None:
        return not_applicable(reason="logging_enabled value uninterpretable", observed=raw)
    if value:
        return passed(logging_enabled=True, expected=True)
    return failed(logging_enabled=False, expected=True)


@rule(
    id="log-retention",
    title="Audit logs retained at least 30 days",
    framework="NIST SP 800-53",
    control="AU-11",
    severity=Severity.low,
    description="Audit records must be retained long enough to support incident investigation.",
    remediation="Configure log retention to 30 days or more.",
)
def log_retention(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_LOG_RETENTION_DAYS)
    if raw is None:
        return not_applicable(reason="log_retention_days attribute not reported")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return not_applicable(reason="log_retention_days not numeric", observed=raw)
    observed = int(raw)
    if observed >= MIN_LOG_RETENTION_DAYS:
        return passed(log_retention_days=observed, threshold_days=MIN_LOG_RETENTION_DAYS)
    return failed(log_retention_days=observed, threshold_days=MIN_LOG_RETENTION_DAYS)


@rule(
    id="backup-recency",
    title="Backed up within the last 7 days",
    framework="NIST SP 800-53",
    control="CP-9",
    severity=Severity.high,
    description="A recent recoverable backup must exist to meet recovery objectives.",
    remediation="Restore the backup schedule; ensure the asset reports a last_backup_at within 7 days.",
)
def backup_recency(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_LAST_BACKUP_AT)
    if raw is None:
        return not_applicable(reason="last_backup_at attribute not reported")
    days = age_days(raw)
    if days is None:
        return not_applicable(reason="last_backup_at value unparsable", observed=raw)
    rounded = round(days, 1)
    if days <= MAX_BACKUP_AGE_DAYS:
        return passed(backup_age_days=rounded, threshold_days=MAX_BACKUP_AGE_DAYS)
    return failed(backup_age_days=rounded, threshold_days=MAX_BACKUP_AGE_DAYS)
