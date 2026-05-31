"""The compliance rule registry.

A *rule* is a small, declarative, framework-control-mapped check that inspects a
single :class:`~app.models.asset.Asset` and returns a
:class:`RuleEvaluation`. Rules register themselves at import time via the
:func:`rule` decorator, which keeps the catalogue data-driven: adding a control
is adding a decorated function, nothing more.

Rules MUST be pure with respect to the database — they read only the in-memory
``asset`` (its ``attributes`` dict and its loaded ``owner``) and return a
status plus an evidence dict. A missing attribute yields
``ComplianceStatus.not_applicable`` ("cannot assess"), never a failure, so we
never penalise an asset for data we simply do not have.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.models.enums import ComplianceStatus, Severity

if TYPE_CHECKING:
    from app.models.asset import Asset


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    """The outcome of evaluating one rule against one asset.

    ``evidence`` captures the observed value and the threshold/expectation so
    the result is audit-defensible without re-running the rule.
    """

    status: ComplianceStatus
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rule:
    """A single compliance control mapped to a real framework reference."""

    id: str
    title: str
    framework: str
    control: str
    severity: Severity
    description: str
    remediation: str
    evaluate: Callable[[Asset], RuleEvaluation]


# Module-level registry, keyed by rule id. Insertion order is preserved (py3.7+)
# and surfaced via get_rules() so the catalogue is deterministic.
_REGISTRY: dict[str, Rule] = {}

# Sentinel flag so the rule packages are imported exactly once.
_loaded = False


def rule(
    *,
    id: str,
    title: str,
    framework: str,
    control: str,
    severity: Severity,
    description: str,
    remediation: str,
) -> Callable[[Callable[[Asset], RuleEvaluation]], Callable[[Asset], RuleEvaluation]]:
    """Decorator that registers the wrapped function as a compliance rule.

    Raises :class:`ValueError` on a duplicate id so two controls can never
    silently collide in the catalogue.
    """

    def _register(
        fn: Callable[[Asset], RuleEvaluation],
    ) -> Callable[[Asset], RuleEvaluation]:
        if id in _REGISTRY:
            raise ValueError(f"Duplicate compliance rule id: {id!r}")
        _REGISTRY[id] = Rule(
            id=id,
            title=title,
            framework=framework,
            control=control,
            severity=severity,
            description=description,
            remediation=remediation,
            evaluate=fn,
        )
        return fn

    return _register


def load_rules() -> None:
    """Import the rule packages so every decorated rule self-registers.

    Idempotent: safe to call repeatedly. The submodules execute their
    ``@rule`` decorators on first import, populating :data:`_REGISTRY`.
    """
    global _loaded
    if _loaded:
        return
    # Importing the package runs its __init__, which imports each rule module.
    importlib.import_module("app.compliance.rules")
    _loaded = True


def get_rules() -> list[Rule]:
    """Return all registered rules in a stable (registration) order."""
    load_rules()
    return list(_REGISTRY.values())


def get_rule(rule_id: str) -> Rule | None:
    """Return a single rule by id, or ``None`` if unknown."""
    load_rules()
    return _REGISTRY.get(rule_id)
