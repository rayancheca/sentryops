"""Rule package: importing it self-registers every compliance rule.

Each submodule decorates its checks with ``@rule(...)`` from
:mod:`app.compliance.registry`, so a plain import is enough to populate the
registry. Order here defines the stable catalogue order returned by
``get_rules()``.
"""

from __future__ import annotations

from app.compliance.rules import (  # noqa: F401  (import side effect: registration)
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
]
