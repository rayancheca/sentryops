"""Shared enumerations.

Kept dependency-free so models, schemas, services, and RBAC can all import them
without creating import cycles.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """RBAC roles, ordered least to most privileged via :meth:`rank`."""

    viewer = "viewer"
    operator = "operator"
    admin = "admin"

    @property
    def rank(self) -> int:
        return {Role.viewer: 0, Role.operator: 1, Role.admin: 2}[self]

    def can_act_as(self, required: Role) -> bool:
        """True when this role meets or exceeds ``required``."""
        return self.rank >= required.rank


class AssetType(StrEnum):
    host = "host"
    network_device = "network_device"
    service = "service"
    software_license = "software_license"
    cloud_resource = "cloud_resource"


class LifecycleState(StrEnum):
    provisioning = "provisioning"
    active = "active"
    maintenance = "maintenance"
    retired = "retired"
    disposed = "disposed"


class Environment(StrEnum):
    prod = "prod"
    staging = "staging"
    dev = "dev"


class Severity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

    @property
    def weight(self) -> int:
        """Severity weight used by compliance scoring."""
        return {
            Severity.low: 1,
            Severity.medium: 2,
            Severity.high: 5,
            Severity.critical: 10,
        }[self]


class ComplianceStatus(StrEnum):
    passed = "pass"
    failed = "fail"
    not_applicable = "not_applicable"


class CheckType(StrEnum):
    http = "http"
    tcp = "tcp"


class CheckStatus(StrEnum):
    up = "up"
    down = "down"


class IncidentStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"
    closed = "closed"


class IncidentEventType(StrEnum):
    opened = "opened"
    ai_triaged = "ai_triaged"
    acknowledged = "acknowledged"
    comment = "comment"
    resolved = "resolved"
    closed = "closed"
    recovered = "recovered"


class AuditAction(StrEnum):
    create = "create"
    update = "update"
    delete = "delete"
    state_change = "state_change"
    checkout = "checkout"
    checkin = "checkin"


class TriageStatus(StrEnum):
    success = "success"
    disabled = "disabled"
    failed = "failed"
