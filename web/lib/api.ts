import type {
  CheckRun,
  Finding,
  Patch,
  PlanSummary,
  Requirement,
  TaskMode,
  TaskState,
} from "./contracts";

export type RepoSource =
  | { kind: "zip"; filename: string }
  | { kind: "git_url"; url: string };

export interface CreateTaskInput {
  repo_source: RepoSource;
  goal: string;
  mode: TaskMode;
}

export interface TaskRecord {
  task_id: string;
  state: TaskState;
  goal: string;
  mode: TaskMode;
  created_at: string;
}

export interface ApprovalRecord {
  approved_plan_digest: string;
  approved_at: string;
}

export interface TaskWorkspace {
  task: TaskRecord;
  requirements: Requirement[];
  checks: CheckRun[];
  findings: Finding[];
  baseline_findings: Finding[];
  patch: Patch | null;
  plan_summary: PlanSummary | null;
  approval: ApprovalRecord | null;
}

export interface CheckSuiteResponse {
  checks: CheckRun[];
  findings: Finding[];
}

export interface PatchResponse {
  patch: Patch;
}

export interface ApprovalResponse {
  task_id: string;
  approved_plan_digest: string;
  approved_at: string;
}

export interface EvidenceReport {
  task_id: string;
  generated_at: string;
  tool_versions: Record<string, string | null>;
  checks: CheckRun[];
  findings: Finding[];
  requirements: Requirement[];
  plan_summary: PlanSummary | null;
  limitations: string[];
}

export class ApiError extends Error {
  readonly kind: "network" | "not_found" | "invalid_response" | "not_configured";

  constructor(
    kind: "network" | "not_found" | "invalid_response" | "not_configured",
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
  }
}

export interface PlanProofApi {
  createTask(input: CreateTaskInput): Promise<TaskRecord>;
  getWorkspace(taskId: string): Promise<TaskWorkspace>;
  runCheckSuite(taskId: string): Promise<CheckSuiteResponse>;
  generatePatch(taskId: string): Promise<PatchResponse>;
  approveTask(taskId: string, planDigest: string): Promise<ApprovalResponse>;
  getEvidenceReport(taskId: string): Promise<EvidenceReport>;
}
