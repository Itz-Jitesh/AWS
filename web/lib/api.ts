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
  | { kind: "zip"; filename: string; file?: File | null }
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
  approval_valid?: boolean | null;
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
  ingest?: IngestSummary | null;
  plan_capture?: PlanCapture | null;
  patch_applied_at?: string | null;
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

export interface PlanCapture {
  available: boolean;
  plan_digest: string | null;
  captured_at: string | null;
  reason: string | null;
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

export type ApiErrorKind =
  | "network"
  | "timeout"
  | "not_found"
  | "invalid_response"
  | "not_configured"
  | "not_supported"
  | "rejected";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string;

  constructor(kind: ApiErrorKind, message: string, options?: { status?: number; code?: string }) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = options?.status;
    this.code = options?.code;
  }
}

export type BackendId = "mock" | "worker-direct" | "orchestration";

export type SupportLevel = "available" | "unverified" | "unavailable";

export type Operation =
  | "createTask"
  | "getWorkspace"
  | "runCheckSuite"
  | "findings"
  | "extractRequirements"
  | "generatePatch"
  | "planSummary"
  | "capturePlan"
  | "approveTask"
  | "getEvidenceReport";

export type SupportMap = Record<Operation, SupportLevel>;

export interface IngestSummary {
  tf_files: Array<{ path: string; size_bytes: number }>;
  providers: Array<{ name: string; source?: string | null; version?: string | null }>;
  warnings: string[];
}

export interface OperationNote {
  level: SupportLevel;
  detail: string;
}

export interface PlanProofApi {
  readonly backend: BackendId;
  readonly support: SupportMap;
  createTask(input: CreateTaskInput): Promise<TaskRecord>;
  getWorkspace(taskId: string): Promise<TaskWorkspace>;
  runCheckSuite(taskId: string): Promise<CheckSuiteResponse>;
  approveTask(taskId: string, planDigest: string): Promise<ApprovalResponse>;
  getEvidenceReport(taskId: string): Promise<EvidenceReport>;
  generatePatch?(taskId: string): Promise<PatchResponse>;
  extractRequirements?(taskId: string, goal: string): Promise<Requirement[]>;
  capturePlan?(taskId: string): Promise<PlanCapture>;
  applyPatch?(taskId: string): Promise<TaskWorkspace>;
  operationNotes?(): Partial<Record<Operation, OperationNote>>;
}
