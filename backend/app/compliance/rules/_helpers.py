"""Shared helpers for compliance rules.

The asset's security-posture facts live in ``asset.attributes`` (a JSONB dict).
The canonical key names mirror ``AssetAttributes`` in
``app/schemas/asset.py``; they are duplicated here as constants so the rules
read a single documented vocabulary and a typo becomes a one-line fix rather
than a scattered string literal.

Convention used by every rule:
    * a *missing* key -> :data:`NOT_APPLICABLE` ("cannot assess"), never a fail
    * a present-but-wrong value -> a fail with evidence
    * a present-and-correct value -> a pass with evidence
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.compliance.registry import RuleEvaluation
from app.models.enums import ComplianceStatus

if TYPE_CHECKING:
    from app.models.asset import Asset

PASS = ComplianceStatus.passed
FAIL = ComplianceStatus.failed
NOT_APPLICABLE = ComplianceStatus.not_applicable

# --- Attribute key vocabulary (mirrors schemas/asset.py::AssetAttributes) ----
ATTR_DISK_ENCRYPTED = "disk_encrypted"
ATTR_ENCRYPTION_IN_TRANSIT = "encryption_in_transit"
ATTR_FIREWALL_ENABLED = "firewall_enabled"
ATTR_LAST_PATCHED_AT = "last_patched_at"
ATTR_HAS_DEFAULT_CREDENTIALS = "has_default_credentials"
ATTR_LOGGING_ENABLED = "logging_enabled"
ATTR_LOG_RETENTION_DAYS = "log_retention_days"
ATTR_LAST_BACKUP_AT = "last_backup_at"
ATTR_OS_SUPPORTED = "os_supported"
ATTR_OPEN_PORTS = "open_ports"
ATTR_TLS_CERT_EXPIRES_AT = "tls_cert_expires_at"
ATTR_EDR_INSTALLED = "edr_installed"
ATTR_ANTIVIRUS_INSTALLED = "antivirus_installed"
ATTR_PASSWORD_MAX_AGE_DAYS = "password_max_age_days"

# Ports that should never be exposed on a managed asset.
#   23/2323 telnet, 445 SMB, 3389 RDP, 21 FTP.
HIGH_RISK_PORTS: frozenset[int] = frozenset({21, 23, 445, 2323, 3389})


def passed(**evidence: Any) -> RuleEvaluation:
    return RuleEvaluation(status=PASS, evidence=evidence)


def failed(**evidence: Any) -> RuleEvaluation:
    return RuleEvaluation(status=FAIL, evidence=evidence)


def not_applicable(**evidence: Any) -> RuleEvaluation:
    return RuleEvaluation(status=NOT_APPLICABLE, evidence=evidence)


def get_attr(asset: Asset, key: str) -> Any | None:
    """Read one posture attribute; ``None`` when the asset has no such key."""
    attributes = asset.attributes or {}
    return attributes.get(key)


def coerce_bool(value: Any) -> bool | None:
    """Best-effort bool coercion that tolerates JSON string/int forms.

    Returns ``None`` for values that cannot be confidently interpreted, so the
    caller can mark the rule not-applicable rather than guess.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on", "enabled"}:
            return True
        if lowered in {"false", "no", "0", "off", "disabled"}:
            return False
    return None


def parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (or epoch seconds) to an aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def age_days(value: Any, *, now: datetime | None = None) -> float | None:
    """Whole-and-fractional days between ``value`` and now; ``None`` if unparsable."""
    parsed = parse_dt(value)
    if parsed is None:
        return None
    reference = now or datetime.now(tz=UTC)
    return (reference - parsed).total_seconds() / 86_400.0


def days_until(value: Any, *, now: datetime | None = None) -> float | None:
    """Whole-and-fractional days from now until ``value``; ``None`` if unparsable."""
    parsed = parse_dt(value)
    if parsed is None:
        return None
    reference = now or datetime.now(tz=UTC)
    return (parsed - reference).total_seconds() / 86_400.0
