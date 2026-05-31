// API types mirroring the backend Pydantic schemas. Keep field names in sync
// with backend/app/schemas/*.

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; details?: unknown } | null;
  meta?: { request_id?: string; total?: number; limit?: number; offset?: number } | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export type Role = "viewer" | "operator" | "admin";
export type AssetType =
  | "host"
  | "network_device"
  | "service"
  | "software_license"
  | "cloud_resource";
export type LifecycleState = "provisioning" | "active" | "maintenance" | "retired" | "disposed";
export type Environment = "prod" | "staging" | "dev";
export type Severity = "low" | "medium" | "high" | "critical";
export type ComplianceStatus = "pass" | "fail" | "not_applicable";
export type IncidentStatus = "open" | "acknowledged" | "resolved" | "closed";
export type CheckType = "http" | "tcp";
export type CheckStatus = "up" | "down";
export type TriageStatus = "success" | "disabled" | "failed";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Tag {
  id: string;
  name: string;
  color: string;
}

export interface Asset {
  id: string;
  short_code: string;
  name: string;
  asset_type: AssetType;
  lifecycle_state: LifecycleState;
  environment: Environment;
  location: string | null;
  description: string | null;
  owner_id: string | null;
  attributes: Record<string, unknown>;
  custom_fields: Record<string, unknown>;
  tags: Tag[];
  created_at: string;
  updated_at: string;
}

export interface AssetListItem {
  id: string;
  short_code: string;
  name: string;
  asset_type: AssetType;
  lifecycle_state: LifecycleState;
  environment: Environment;
  owner_id: string | null;
}

export interface DependencyNode {
  id: string;
  name: string;
  asset_type: AssetType;
}
export interface DependencyEdge {
  source_asset_id: string;
  target_asset_id: string;
  kind?: string | null;
}
export interface DependencyTree {
  asset: DependencyNode;
  nodes: DependencyNode[];
  edges: DependencyEdge[];
}

export interface ComplianceRule {
  id: string;
  title: string;
  framework: string;
  control: string;
  severity: Severity;
  description: string;
  remediation: string;
}

export interface ComplianceResult {
  id: string;
  run_id: string;
  asset_id: string;
  rule_id: string;
  status: ComplianceStatus;
  severity: Severity;
  evidence: Record<string, unknown> | null;
  created_at: string;
}

export interface ComplianceRun {
  id: string;
  started_at: string;
  finished_at: string | null;
  org_score: number;
  total_assets: number;
  passed_count: number;
  failed_count: number;
  not_applicable_count: number;
  severity_failing: Record<string, number>;
}

export interface DriftPoint {
  run_id: string;
  started_at: string;
  org_score: number;
  severity_failing: Record<string, number>;
}

export interface Service {
  id: string;
  name: string;
  description: string | null;
  asset_id: string | null;
  slo_target: number;
}

export interface HealthCheck {
  id: string;
  service_id: string;
  name: string;
  check_type: CheckType;
  target: string;
  method: string;
  expected_status: number;
  latency_budget_ms: number;
  port: number | null;
  interval_seconds: number;
  enabled: boolean;
}

export interface StatusGridItem {
  service_id: string;
  service_name: string;
  status: CheckStatus;
  uptime_24h: number;
  slo_target: number;
  open_incidents: number;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  severity: Severity;
  service_id: string;
  asset_id: string | null;
  health_check_id: string | null;
  opened_at: string;
  acknowledged_at: string | null;
  acknowledged_by_id: string | null;
  resolved_at: string | null;
  resolved_by_id: string | null;
  closed_at: string | null;
}

export interface IncidentEvent {
  id: string;
  event_type: string;
  message: string | null;
  actor_id: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface RemediationStep {
  step: string;
  rationale?: string | null;
  priority?: number;
}

export interface TriageResult {
  id: string;
  incident_id: string;
  status: TriageStatus;
  model: string | null;
  root_cause_hypothesis: string | null;
  confidence: number | null;
  severity_assessment: Severity | null;
  remediation_steps: RemediationStep[] | null;
  stakeholder_comms_draft: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  is_seeded: boolean;
  created_at: string;
}

export interface MttaMttr {
  mtta_seconds: number | null;
  mttr_seconds: number | null;
  window_hours: number | null;
}
