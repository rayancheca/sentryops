"""Seed realistic demo data so the dashboards look alive on first load.

Run with: python -m scripts.seed   (set RESEED=1 to wipe and reseed).

Creates accounts, ~30 assets with a real-looking dependency topology and
deliberate compliance violations across severities, services with check
history, historical compliance snapshots (for the drift chart), three incidents
(one open/critical, two resolved that feed MTTA/MTTR), recent audit-log changes
(the AI agent's "what changed"), and clearly-labelled illustrative AI triage.
"""

from __future__ import annotations

import os
import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.asset import Asset, AssetDependency, Tag
from app.models.audit import AuditLog
from app.models.compliance import ComplianceRun
from app.models.enums import (
    AssetType,
    AuditAction,
    CheckStatus,
    CheckType,
    Environment,
    IncidentEventType,
    IncidentStatus,
    LifecycleState,
    Role,
    Severity,
)
from app.models.observability import (
    CheckResult,
    HealthCheck,
    Incident,
    IncidentEvent,
    Service,
)
from app.models.user import User
from app.services.compliance_service import run_evaluation

random.seed(7)  # deterministic demo data
NOW = datetime.now(UTC)
TODAY = NOW.date()


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def days_ahead(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


# Fully-compliant posture; per-asset overrides introduce specific violations.
COMPLIANT: dict[str, Any] = {
    "disk_encryption": True,
    "firewall_enabled": True,
    "last_patched_at": days_ago(8),
    "os_name": "Ubuntu",
    "os_version": "22.04 LTS",
    "os_eol": False,
    "backup_last_at": days_ago(1),
    "open_ports": [443, 22],
    "tls_cert_expires_at": days_ahead(180),
    "edr_present": True,
    "antivirus_present": True,
    "default_credentials": False,
    "logging_enabled": True,
    "encryption_in_transit": True,
    "password_max_age_days": 60,
    "log_retention_days": 90,
}


def attrs(**overrides: Any) -> dict[str, Any]:
    merged = dict(COMPLIANT)
    merged.update(overrides)
    return merged


def wipe(db: Any) -> None:
    from app.db.base import Base

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.commit()


def make_user(db: Any, email: str, name: str, role: Role, password: str, mfa: bool) -> User:
    user = User(
        email=email,
        full_name=name,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
        mfa_enabled=mfa,
    )
    db.add(user)
    return user


def seed() -> None:  # noqa: PLR0915 - a linear seed script reads best top-to-bottom
    settings = get_settings()
    db = SessionLocal()
    try:
        existing = db.scalar(select(func.count()).select_from(Asset))
        if existing and not os.environ.get("RESEED"):
            print(f"Already seeded ({existing} assets). Set RESEED=1 to wipe and reseed.")
            return
        if os.environ.get("RESEED"):
            wipe(db)

        # --- Accounts -------------------------------------------------------
        admin = make_user(
            db, settings.first_admin_email, "Ops Admin", Role.admin,
            settings.first_admin_password, mfa=True,
        )
        operator = make_user(
            db, "operator@sentryops.local", "On-Call Operator", Role.operator,
            "operator12345", mfa=True,
        )
        make_user(
            db, settings.first_viewer_email, "Read-Only Viewer", Role.viewer,
            settings.first_viewer_password, mfa=False,
        )
        marco = make_user(db, "marco.sre@sentryops.local", "Marco (SRE)", Role.operator, "demo12345", True)
        dana = make_user(db, "dana.ops@sentryops.local", "Dana (Ops)", Role.operator, "demo12345", False)
        priya = make_user(db, "priya.sec@sentryops.local", "Priya (Security)", Role.admin, "demo12345", True)
        db.flush()

        # --- Tags -----------------------------------------------------------
        tag_names = {
            "prod-critical": "#ef4444",
            "pci": "#f59e0b",
            "internet-facing": "#38bdf8",
            "internal": "#64748b",
            "legacy": "#a78bfa",
            "kubernetes": "#22d3ee",
            "database": "#34d399",
        }
        tags = {name: Tag(name=name, color=color) for name, color in tag_names.items()}
        db.add_all(tags.values())
        db.flush()

        # --- Assets ---------------------------------------------------------
        # (name, type, env, owner, location, [tag names], attribute overrides)
        owners = {"marco": marco, "dana": dana, "priya": priya, "admin": admin}
        spec: list[tuple] = [
            ("web-app-01", AssetType.host, Environment.prod, "marco", "us-east-1a",
             ["prod-critical", "internet-facing"], {}),
            ("web-app-02", AssetType.host, Environment.prod, "marco", "us-east-1b",
             ["prod-critical", "internet-facing"], {"backup_last_at": days_ago(11)}),
            ("api-gateway-01", AssetType.host, Environment.prod, "marco", "us-east-1a",
             ["prod-critical", "internet-facing"], {"open_ports": [443, 80, 22]}),
            ("auth-service", AssetType.service, Environment.prod, "priya", "us-east-1",
             ["prod-critical", "pci"], {}),
            ("billing-service", AssetType.service, Environment.prod, "dana", "us-east-1",
             ["prod-critical", "pci"], {"tls_cert_expires_at": days_ahead(9), "encryption_in_transit": False}),
            ("search-es", AssetType.service, Environment.prod, "marco", "us-east-1",
             ["internal"], {"logging_enabled": False}),
            ("postgres-primary", AssetType.service, Environment.prod, "dana", "us-east-1",
             ["prod-critical", "database", "pci"], {"open_ports": [5432, 22, 3389], "backup_last_at": days_ago(1)}),
            ("postgres-replica", AssetType.service, Environment.prod, "dana", "us-east-1",
             ["database"], {"open_ports": [5432, 22]}),
            ("redis-cache", AssetType.service, Environment.prod, "marco", "us-east-1",
             ["internal"], {"default_credentials": True}),
            ("rabbitmq", AssetType.service, Environment.prod, "marco", "us-east-1",
             ["internal"], {}),
            ("worker-01", AssetType.host, Environment.prod, "marco", "us-east-1a", ["internal"], {}),
            ("worker-02", AssetType.host, Environment.prod, "dana", "us-east-1b",
             ["internal"], {"edr_present": False}),
            ("bastion-01", AssetType.host, Environment.prod, "priya", "us-east-1",
             ["internet-facing"], {"open_ports": [22]}),
            ("core-switch-01", AssetType.network_device, Environment.prod, "priya", "dc-rack-4",
             ["internal"], {"os_name": "Cisco IOS", "os_version": "15.2", "edr_present": False, "antivirus_present": False}),
            ("edge-firewall-01", AssetType.network_device, Environment.prod, "priya", "dc-rack-1",
             ["internet-facing"], {"os_name": "PAN-OS", "os_version": "10.2", "edr_present": False, "antivirus_present": False}),
            ("vpn-gateway-01", AssetType.network_device, Environment.prod, "priya", "dc-rack-1",
             ["internet-facing"], {"os_name": "PAN-OS", "os_version": "9.1", "os_eol": True, "edr_present": False, "antivirus_present": False}),
            ("legacy-erp", AssetType.host, Environment.prod, "dana", "on-prem-dc",
             ["legacy"], {"os_name": "Windows Server", "os_version": "2012 R2", "os_eol": True,
                          "last_patched_at": days_ago(210), "disk_encryption": False, "edr_present": False}),
            ("jenkins-ci", AssetType.host, Environment.staging, "marco", "us-east-1",
             ["internal"], {"last_patched_at": days_ago(64)}),
            ("k8s-prod-cluster", AssetType.cloud_resource, Environment.prod, "marco", "us-east-1",
             ["prod-critical", "kubernetes"], {}),
            ("k8s-staging-cluster", AssetType.cloud_resource, Environment.staging, "marco", "us-east-1",
             ["kubernetes"], {}),
            ("s3-backups", AssetType.cloud_resource, Environment.prod, "dana", "us-east-1",
             ["internal"], {"open_ports": []}),
            ("cdn-edge", AssetType.cloud_resource, Environment.prod, "marco", "global",
             ["internet-facing"], {}),
            ("rds-analytics", AssetType.cloud_resource, Environment.prod, "dana", "us-west-2",
             ["database"], {"backup_last_at": days_ago(20)}),
            ("object-store", AssetType.cloud_resource, Environment.prod, "marco", "us-east-1",
             ["internal"], {}),
            ("grafana", AssetType.service, Environment.prod, "marco", "us-east-1", ["internal"], {}),
            ("prometheus", AssetType.service, Environment.prod, "marco", "us-east-1", ["internal"], {}),
            ("vmware-vsphere", AssetType.software_license, Environment.prod, "priya", "on-prem-dc",
             ["internal"], {"os_name": "vSphere", "os_version": "7.0", "edr_present": False, "antivirus_present": False}),
            ("datadog-seats", AssetType.software_license, Environment.prod, "admin", "saas",
             ["internal"], {"edr_present": False, "antivirus_present": False, "disk_encryption": False}),
            ("office365-tenant", AssetType.software_license, Environment.prod, None, "saas",
             ["internal"], {"edr_present": False, "antivirus_present": False, "disk_encryption": False}),
            ("dev-sandbox-01", AssetType.host, Environment.dev, None, "us-east-1",
             ["internal"], {"firewall_enabled": False, "logging_enabled": False}),
        ]

        assets: dict[str, Asset] = {}
        for name, atype, env, owner_key, loc, tnames, over in spec:
            a = Asset(
                short_code="",  # set by service in real flow; deterministic here
                name=name,
                asset_type=atype,
                lifecycle_state=LifecycleState.active,
                environment=env,
                location=loc,
                owner_id=owners[owner_key].id if owner_key else None,
                attributes=attrs(**over),
                tags=[tags[t] for t in tnames],
            )
            a.short_code = f"{atype.value[:3].upper()}-{abs(hash(name)) % 100000:05d}"
            assets[name] = a
            db.add(a)
        db.flush()

        # --- Dependency topology (source depends on target) -----------------
        edges = [
            ("web-app-01", "postgres-primary"), ("web-app-01", "redis-cache"), ("web-app-01", "auth-service"),
            ("web-app-02", "postgres-primary"), ("web-app-02", "redis-cache"), ("web-app-02", "auth-service"),
            ("api-gateway-01", "web-app-01"), ("api-gateway-01", "web-app-02"), ("api-gateway-01", "cdn-edge"),
            ("auth-service", "postgres-primary"), ("auth-service", "redis-cache"),
            ("billing-service", "postgres-primary"), ("billing-service", "rabbitmq"),
            ("postgres-replica", "postgres-primary"),
            ("worker-01", "rabbitmq"), ("worker-01", "postgres-primary"),
            ("worker-02", "rabbitmq"), ("search-es", "object-store"),
            ("rds-analytics", "postgres-replica"), ("grafana", "prometheus"),
            ("web-app-01", "k8s-prod-cluster"), ("billing-service", "k8s-prod-cluster"),
        ]
        for src, dst in edges:
            db.add(AssetDependency(source_asset_id=assets[src].id, target_asset_id=assets[dst].id, kind="depends_on"))
        db.flush()

        # --- Services + health checks --------------------------------------
        svc_spec = [
            ("Public API", "api-gateway-01", 0.999, "https://api.demo.local/healthz"),
            ("Auth Service", "auth-service", 0.999, "https://auth.demo.local/healthz"),
            ("Billing Service", "billing-service", 0.995, "https://billing.demo.local/healthz"),
            ("Search", "search-es", 0.99, "https://search.demo.local/_cluster/health"),
            ("Web App", "web-app-01", 0.999, "https://app.demo.local/healthz"),
        ]
        services: dict[str, Service] = {}
        checks: dict[str, HealthCheck] = {}
        for sname, asset_name, slo, url in svc_spec:
            svc = Service(name=sname, description=f"{sname} synthetic monitor",
                          asset_id=assets[asset_name].id, slo_target=slo)
            db.add(svc)
            db.flush()
            chk = HealthCheck(service_id=svc.id, name=f"{sname} HTTP", check_type=CheckType.http,
                              target=url, method="GET", expected_status=200, latency_budget_ms=800,
                              interval_seconds=60, enabled=True)
            db.add(chk)
            services[sname] = svc
            checks[sname] = chk
        db.flush()

        # --- Check-result history (mostly up; Billing currently down) -------
        for sname, chk in checks.items():
            down_now = sname == "Billing Service"
            for i in range(60):  # ~60 minutes of history
                ts = NOW - timedelta(minutes=i)
                is_down = down_now and i < 6  # last 6 minutes down for Billing
                db.add(CheckResult(
                    health_check_id=chk.id,
                    status=CheckStatus.down if is_down else CheckStatus.up,
                    latency_ms=None if is_down else round(random.uniform(40, 220), 1),
                    status_code=503 if is_down else 200,
                    error="connection refused" if is_down else None,
                    created_at=ts,
                ))
        db.flush()

        # --- Recent audit changes (the AI agent's "what changed") -----------
        db.add(AuditLog(
            actor_id=dana.id, action=AuditAction.update, entity_type="asset",
            entity_id=assets["postgres-primary"].id, source_ip="10.0.4.21",
            before={"attributes": {"max_connections": 500}},
            after={"attributes": {"max_connections": 120}},
            created_at=NOW - timedelta(hours=3),
        ))
        db.add(AuditLog(
            actor_id=marco.id, action=AuditAction.state_change, entity_type="asset",
            entity_id=assets["billing-service"].id, source_ip="10.0.4.30",
            before={"lifecycle_state": "maintenance"}, after={"lifecycle_state": "active"},
            created_at=NOW - timedelta(hours=2, minutes=40),
        ))
        db.flush()

        # --- Incidents ------------------------------------------------------
        def event(inc: Incident, etype: IncidentEventType, msg: str, when: datetime, actor: User | None = None) -> None:
            db.add(IncidentEvent(incident_id=inc.id, event_type=etype, message=msg,
                                 actor_id=actor.id if actor else None, created_at=when))

        # 1) OPEN, critical — Billing down
        billing = Incident(
            service_id=services["Billing Service"].id, health_check_id=checks["Billing Service"].id,
            asset_id=assets["billing-service"].id, title="Billing Service is failing health checks",
            status=IncidentStatus.open, severity=Severity.critical, opened_at=NOW - timedelta(hours=2, minutes=10),
        )
        db.add(billing)
        db.flush()
        event(billing, IncidentEventType.opened, "Opened after 3 consecutive failed checks.", NOW - timedelta(hours=2, minutes=10))

        # 2) RESOLVED — Search (feeds MTTA/MTTR)
        search = Incident(
            service_id=services["Search"].id, health_check_id=checks["Search"].id,
            asset_id=assets["search-es"].id, title="Search latency breached SLO",
            status=IncidentStatus.closed, severity=Severity.high,
            opened_at=NOW - timedelta(days=3), acknowledged_at=NOW - timedelta(days=3) + timedelta(minutes=9),
            acknowledged_by_id=operator.id, resolved_at=NOW - timedelta(days=3) + timedelta(minutes=52),
            resolved_by_id=operator.id, closed_at=NOW - timedelta(days=3) + timedelta(minutes=52),
        )
        db.add(search)
        db.flush()
        event(search, IncidentEventType.opened, "Opened after sustained latency over budget.", search.opened_at)
        event(search, IncidentEventType.acknowledged, "Acknowledged by on-call.", search.acknowledged_at, operator)
        event(search, IncidentEventType.comment, "Rolling index merge throttled; raising heap.", search.acknowledged_at + timedelta(minutes=14), operator)
        event(search, IncidentEventType.resolved, "Latency recovered; closing.", search.resolved_at, operator)
        event(search, IncidentEventType.closed, "Check green for 2 consecutive runs.", search.closed_at)

        # 3) RESOLVED — Auth blip (feeds MTTA/MTTR)
        auth = Incident(
            service_id=services["Auth Service"].id, health_check_id=checks["Auth Service"].id,
            asset_id=assets["auth-service"].id, title="Auth Service brief 5xx spike",
            status=IncidentStatus.closed, severity=Severity.medium,
            opened_at=NOW - timedelta(hours=26), acknowledged_at=NOW - timedelta(hours=26) + timedelta(minutes=4),
            acknowledged_by_id=marco.id, resolved_at=NOW - timedelta(hours=26) + timedelta(minutes=23),
            resolved_by_id=marco.id, closed_at=NOW - timedelta(hours=26) + timedelta(minutes=23),
        )
        db.add(auth)
        db.flush()
        event(auth, IncidentEventType.opened, "Opened after 3 failed checks.", auth.opened_at)
        event(auth, IncidentEventType.acknowledged, "Acknowledged.", auth.acknowledged_at, marco)
        event(auth, IncidentEventType.resolved, "Transient pod eviction; recovered.", auth.resolved_at, marco)
        event(auth, IncidentEventType.closed, "Closed.", auth.closed_at)
        db.flush()

        # --- Seeded illustrative AI triage ---------------------------------
        from app.ai.triage import seed_triage

        seed_triage(db, billing, {
            "root_cause_hypothesis": (
                "Billing Service health checks began failing shortly after a configuration change to its "
                "upstream dependency postgres-primary: max_connections was lowered from 500 to 120 about 3 "
                "hours ago (see audit log). Billing likely exhausted its database connection pool, returning "
                "503s on the /healthz probe."
            ),
            "confidence": 0.72,
            "severity_assessment": "critical",
            "remediation_steps": [
                {"step": "Revert the postgres-primary max_connections change (120 -> 500) recorded in the audit log ~3h ago.",
                 "rationale": "The outage correlates tightly with that change; reverting is the fastest path to recovery.", "priority": 1},
                {"step": "Restart billing-service workers to clear stuck/exhausted connections.",
                 "rationale": "Clears stale pooled connections after the upstream fix.", "priority": 2},
                {"step": "Verify postgres-primary health (active connections, replication lag) before resolving.",
                 "rationale": "Rules out a deeper database fault.", "priority": 3},
            ],
            "stakeholder_comms_draft": (
                "We are aware of an issue affecting Billing Service that began around 14:20 UTC. Customers may "
                "experience errors when processing payments. We have identified a likely cause related to a recent "
                "database configuration change and are rolling it back. Next update in 30 minutes."
            ),
        })
        event(billing, IncidentEventType.ai_triaged, "AI triage completed (illustrative).", NOW - timedelta(hours=2, minutes=8))

        seed_triage(db, search, {
            "root_cause_hypothesis": "Sustained search latency traced to an unthrottled segment merge under heavy indexing load.",
            "confidence": 0.64,
            "severity_assessment": "high",
            "remediation_steps": [
                {"step": "Throttle index merges and raise JVM heap on search-es.", "rationale": "Relieves GC pressure driving latency.", "priority": 1},
                {"step": "Add a queue-depth alert ahead of SLO breach.", "rationale": "Earlier detection next time.", "priority": 2},
            ],
            "stakeholder_comms_draft": "Search was briefly slow due to background index maintenance. Service has recovered; no data was lost.",
        })
        db.flush()

        # --- Compliance: historical snapshots (drift) + a real latest run ---
        history = [
            (28, 71.0, {"critical": 4, "high": 9, "medium": 6, "low": 3}),
            (24, 73.5, {"critical": 3, "high": 8, "medium": 6, "low": 3}),
            (19, 70.2, {"critical": 4, "high": 10, "medium": 5, "low": 2}),
            (14, 76.8, {"critical": 3, "high": 7, "medium": 5, "low": 2}),
            (9, 79.1, {"critical": 2, "high": 7, "medium": 4, "low": 2}),
            (4, 81.0, {"critical": 2, "high": 6, "medium": 4, "low": 2}),
        ]
        for d, score, sev in history:
            started = NOW - timedelta(days=d)
            db.add(ComplianceRun(
                started_at=started, finished_at=started + timedelta(seconds=12),
                triggered_by_id=priya.id, total_assets=len(assets),
                org_score=score, passed_count=0, failed_count=sum(sev.values()),
                not_applicable_count=0, severity_failing=sev,
            ))
        db.commit()

        run = run_evaluation(db, admin)  # real latest run with per-asset results
        db.commit()
        print(
            f"Seeded {len(assets)} assets, {len(edges)} dependencies, {len(services)} services, "
            f"3 incidents, {len(history) + 1} compliance runs. Latest org score: {run.org_score:.1f}%."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
