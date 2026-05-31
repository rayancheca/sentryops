# Adding a Compliance Rule

SentryOps' compliance engine is a registry of small, pure, framework-mapped checks. Each rule inspects one `Asset` and returns a status plus evidence. Adding a control is adding one decorated function. There is no schema migration, no service change, and no rearchitecting: the registry is data-driven, the scoring math is generic over severity, and the engine already walks every active asset against every registered rule.

This guide shows exactly where the pieces live, the decorator contract, how severity and control mapping work, and a copy-paste example you can drop in.

## How the engine finds your rule

The moving parts live under `backend/app/compliance/`:

```text
backend/app/compliance/
├── registry.py          # the @rule decorator + the Rule / RuleEvaluation dataclasses
├── engine.py            # (orchestration entrypoint; rules are evaluated by the service)
├── rules/
│   ├── __init__.py      # imports every rule module — this is what registers them
│   ├── _helpers.py      # shared attribute-key constants + pass/fail/N-A + parsing helpers
│   ├── encryption.py
│   ├── endpoint.py
│   ├── identity.py
│   ├── logging_backup.py
│   ├── network.py
│   └── patching.py
```

Registration is import-time and side-effect based. `registry.load_rules()` does `importlib.import_module("app.compliance.rules")`, and that package's `__init__.py` imports each submodule. Importing a submodule runs its `@rule(...)` decorators, and each decorator inserts a `Rule` into the module-level `_REGISTRY` dict. `get_rules()` returns the registry's values in stable insertion order.

So a new rule becomes live when two things are true:

1. It is defined with the `@rule(...)` decorator in a module under `app/compliance/rules/`.
2. That module is imported by `app/compliance/rules/__init__.py`.

Nothing else calls your function directly. `compliance_service.run_evaluation` loads every active asset, calls `rule.evaluate(asset)` for every registered rule, and persists one `ComplianceResult` per (asset, rule) with the rule's `severity` denormalized onto the row.

## The decorator contract

The decorator is defined in `app/compliance/registry.py`. Every keyword is required:

```python
def rule(
    *,
    id: str,          # unique catalogue id; a duplicate raises ValueError at import
    title: str,       # human-readable control name shown in reports
    framework: str,   # e.g. "NIST SP 800-53" or "CIS Benchmark"
    control: str,     # the specific control reference, e.g. "SC-28"
    severity: Severity,  # low | medium | high | critical
    description: str, # what the control protects against
    remediation: str, # the concrete fix shown in the audit-ready report
) -> ...
```

The decorated function has the signature `Callable[[Asset], RuleEvaluation]` and **must be pure with respect to the database**. It reads only the in-memory `asset` (its `attributes` dict and its eagerly loaded `owner`) and returns a `RuleEvaluation`. Do not query the session, hit the network, or mutate the asset.

Return one of three statuses, using the helpers from `app/compliance/rules/_helpers.py`:

| Helper | Status | When |
|--------|--------|------|
| `passed(**evidence)` | `pass` | The control holds. Weight counts toward earned and applicable. |
| `failed(**evidence)` | `fail` | The control is violated. Weight counts toward applicable only. |
| `not_applicable(**evidence)` | `not_applicable` | The fact needed to assess is missing or uninterpretable. Excluded from the score entirely. |

The cardinal convention, enforced across every existing rule: **a missing attribute is `not_applicable`, never `fail`.** An asset is never penalized for data we simply do not have. Put the observed value and the threshold/expectation into the evidence kwargs so the result is audit-defensible without re-running the rule.

## How severity and control mapping work

`severity` is a `Severity` enum member (`app/models/enums.py`). It does two things:

1. **It is the scoring weight.** `Severity.weight` maps `low=1, medium=2, high=5, critical=10`. `compliance.scoring.asset_score` computes `100 * (Σ weight of passed applicable rules) / (Σ weight of passed+failed applicable rules)`, so a failing `critical` rule moves the score ten times as much as a failing `low` one. Pick severity by the real blast radius of the failure, not by gut feel.
2. **It is denormalized onto each result row.** When the engine persists a `ComplianceResult`, it copies `rule.severity` onto the row. Historical runs keep the severity they were scored with even if you later change the rule, so drift charts stay honest.

`framework` and `control` are reporting metadata. They flow straight through to the audit-ready report (`compliance_service.report`) and the "newly failing" diff, where they label each failing control with its framework reference and remediation text. Use real references (the existing rules map to NIST SP 800-53 and CIS Benchmark controls such as `SC-28`, `IA-2`, `SI-2`, `CP-9`, `AU-11`). The string is free-form, so a "primary (also secondary)" form like `"SC-28 (also CIS Benchmark)"` is fine.

## The attribute vocabulary

Rules read posture facts from `asset.attributes` (a JSONB dict) through `get_attr(asset, KEY)`, which returns `None` when the key is absent. The canonical key names are defined once as constants in `_helpers.py` so a typo is a one-line fix rather than a scattered string literal. The keys that already exist:

```text
disk_encrypted          encryption_in_transit   firewall_enabled
last_patched_at         has_default_credentials logging_enabled
log_retention_days      last_backup_at          os_supported
open_ports              tls_cert_expires_at     edr_installed
antivirus_installed     password_max_age_days
```

The owner-MFA rule is the one exception that reads a real column (`asset.owner.mfa_enabled`) instead of the attributes bag; the compliance service eager-loads `Asset.owner` precisely so that rule can run without a query.

`_helpers.py` also gives you safe parsers so you never trust raw JSON:

- `coerce_bool(value)` — tolerant bool coercion (`"true"`, `1`, `"enabled"` …); returns `None` when uninterpretable, so you can mark the rule `not_applicable` rather than guess.
- `parse_dt(value)` / `age_days(value)` / `days_until(value)` — timezone-aware date handling that returns `None` on unparsable input.

If you introduce a new attribute, add its key constant to `_helpers.py` and (for type-completeness) the corresponding optional field to `AssetAttributes` in `app/schemas/asset.py`, which uses `extra="allow"` so unknown keys are never dropped on round-trip.

## Worked example: minimum RAM for production hosts

Suppose you want a control that fails a production host reporting less than 8 GB of RAM. Two steps.

**Step 1 — add the attribute key** to `app/compliance/rules/_helpers.py` (next to the other `ATTR_*` constants):

```python
ATTR_MEMORY_GB = "memory_gb"
```

**Step 2 — create the rule file** `app/compliance/rules/capacity.py`:

```python
"""Capacity controls: minimum provisioned resources."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.compliance.registry import RuleEvaluation, rule
from app.compliance.rules._helpers import (
    ATTR_MEMORY_GB,
    failed,
    get_attr,
    not_applicable,
    passed,
)
from app.models.enums import Severity

if TYPE_CHECKING:
    from app.models.asset import Asset

# Minimum provisioned memory, in GB, for a managed host.
MIN_MEMORY_GB = 8


@rule(
    id="min-memory",
    title="Host meets minimum memory baseline",
    framework="CIS Benchmark",
    control="CM-6 (also NIST SP 800-53)",
    severity=Severity.medium,
    description="Under-provisioned hosts risk OOM-driven outages and cannot run the required security agents.",
    remediation="Increase the host's provisioned memory to at least 8 GB.",
)
def min_memory(asset: Asset) -> RuleEvaluation:
    raw = get_attr(asset, ATTR_MEMORY_GB)
    if raw is None:
        return not_applicable(reason="memory_gb attribute not reported")
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return not_applicable(reason="memory_gb not numeric", observed=raw)
    observed = float(raw)
    if observed >= MIN_MEMORY_GB:
        return passed(memory_gb=observed, threshold_gb=MIN_MEMORY_GB)
    return failed(memory_gb=observed, threshold_gb=MIN_MEMORY_GB)
```

**Step 3 — register the module** by adding it to `app/compliance/rules/__init__.py`:

```python
from app.compliance.rules import (  # noqa: F401  (import side effect: registration)
    capacity,        # <-- add
    encryption,
    endpoint,
    identity,
    logging_backup,
    network,
    patching,
)

__all__ = [
    "encryption",
    "patching",
    "identity",
    "network",
    "logging_backup",
    "endpoint",
    "capacity",      # <-- add
]
```

That is the entire change. The next compliance run picks up `min-memory` automatically: it is evaluated against every active asset, scored with `medium` weight (2), and surfaced in the report with its CM-6 reference and remediation text. Assets that do not report `memory_gb` are `not_applicable` and unaffected.

## Checklist

- [ ] Rule lives in a module under `app/compliance/rules/`.
- [ ] The module is imported by `rules/__init__.py` (and listed in `__all__`).
- [ ] `id` is unique (a duplicate raises `ValueError` at import time).
- [ ] Severity reflects real blast radius (it is the scoring weight: low 1, medium 2, high 5, critical 10).
- [ ] `framework` / `control` use real references; `remediation` is a concrete, actionable fix.
- [ ] A missing attribute returns `not_applicable`, never `failed`.
- [ ] The function reads only the in-memory `asset`; it does not touch the database.
- [ ] Any new attribute key is added to `_helpers.py` (and ideally `AssetAttributes` in `schemas/asset.py`).
- [ ] Evidence kwargs record the observed value and the threshold/expectation.
