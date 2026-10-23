export const SCHEMA_VERSION = "1.0.0" as const;

export type CheckStatus =
  | "Passed"
  | "Failed"
  | "Skipped"
  | "NotConfigured"
  | "UnableToVerify";

export type Severity =
  | "critical"
  | "high"
  | "medium"
  | "low"
  | "info"
  | "unknown";

export type RuleSource = "checkov" | "opa" | "terraform" | "custom";

export type RequirementStatus = "Satisfied" | "Unverified" | "Violated";

export type PlanAction = "create" | "update" | "delete" | "read" | "no-op";

export type DestructiveRisk = "high" | "medium" | "low";

export type TaskMode = "audit" | "build";

export type TaskState =
  | "CREATED"
  | "CONTEXT_GATHERING"
  | "REQUIREMENTS_READY"
  | "PROPOSED"
  | "CHECKING"
  | "REPAIRING"
  | "REVIEW_READY"
  | "AWAITING_APPROVAL"
  | "COMPLETE";

export interface CheckRun {
  schema_version: typeof SCHEMA_VERSION;
  check_id: string;
  tool: string;
  status: CheckStatus;
  started_at: string;
  duration_ms: number;
  summary: string;
  exit_code?: number | null;
  tool_version?: string | null;
  stdout_artifact?: string | null;
  stderr_artifact?: string | null;
  limitations?: string[];
}

export interface Finding {
  schema_version: typeof SCHEMA_VERSION;
  finding_id: string;
  rule_source: RuleSource;
  rule_id: string;
  severity: Severity;
  status: CheckStatus;
  title: string;
  description?: string;
  resource_address?: string | null;
  file_path?: string | null;
  line_start?: number | null;
  evidence: string;
  remediation?: string | null;
  fingerprint: string;
}

export interface Requirement {
  schema_version: typeof SCHEMA_VERSION;
  requirement_id: string;
  text: string;
  mandatory: boolean;
  status: RequirementStatus;
  evidence?: string[];
  notes?: string;
}

export interface Patch {
  schema_version: typeof SCHEMA_VERSION;
  patch_id: string;
  unified_diff: string;
  rationale: string;
  files_changed: string[];
  base_digest: string;
  model_id?: string | null;
  warnings?: string[];
}

export interface DestructiveAction {
  address: string;
  actions: PlanAction[];
  risk: DestructiveRisk;
  reason?: string;
}

export interface PlanSummary {
  schema_version: typeof SCHEMA_VERSION;
  plan_digest: string;
  create: number;
  update: number;
  replace: number;
  destroy: number;
  destructive_actions: DestructiveAction[];
  has_changes: boolean;
}
