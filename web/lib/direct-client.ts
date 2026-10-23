import {
  ApiError,
  type ApprovalResponse,
  type BackendId,
  type CheckSuiteResponse,
  type CreateTaskInput,
  type EvidenceReport,
  type IngestSummary,
  type PatchResponse,
  type PlanCapture,
  type PlanProofApi,
  type SupportMap,
  type TaskRecord,
  type TaskWorkspace,
} from "./api";
import type { CheckRun, Requirement, TaskState } from "./contracts";
import { requestJson } from "./http";
import { DIGEST_PATTERN, isCheckRunList, isRequirementList } from "./validate";

export const WORKER_BACKEND: BackendId = "worker-direct";

const TASK_ID_PATTERN = /^[0-9a-f]{32}$/;

const MANDATORY_CHECKS = ["fmt", "init", "validate", "plan", "show_json"] as const;

const CACHE_KEY_PREFIX = "planproof:direct:";

const NO_READ_MODEL_NOTE =
  "GET /tasks/{id} (task read model) is not implemented. This task's state lives in this browser session only. Owner: Agent B (DEC-07).";

const NOTES = {
  createTask: {
    level: "available" as const,
    detail: "POST /ingest (git_url) and POST /ingest/upload (zip) on the worker service.",
  },
  getWorkspace: {
    level: "available" as const,
    detail: "Composed from this session's cache; no server task read endpoint exists (DEC-07 pending).",
  },
  runCheckSuite: {
    level: "available" as const,
    detail: "POST /check with the full mandatory set fmt, init, validate, plan, show_json (DEC-INT-02).",
  },
  findings: {
    level: "unavailable" as const,
    detail:
      "No findings endpoint exists. The audit service is a library without HTTP; wiring requires the orchestration service (owners Agent B / Agent D).",
  },
  extractRequirements: {
    level: "unavailable" as const,
    detail: "Replaced at runtime — see runtimeNotes().",
  },
  generatePatch: {
    level: "unavailable" as const,
    detail:
      "Agent C exposes POST /tasks/{id}/patch but it requires a server-resolved workspace path; the frontend must not send workspace paths (DEC-INT-04/DEC-INT-05). Blocked on the orchestration service.",
  },
  planSummary: {
    level: "unavailable" as const,
    detail:
      "Plan classification (plan_digest + counts) needs audit library integration server-side; the worker only captures raw plan JSON.",
  },
  capturePlan: {
    level: "available" as const,
    detail: "POST /capture on the worker service; returns the SHA-256 digest of the captured plan.",
  },
  approveTask: {
    level: "unavailable" as const,
    detail: "POST /tasks/{id}/approve is not implemented. Owner: Agent B (DEC-05).",
  },
  getEvidenceReport: {
    level: "unavailable" as const,
    detail: "GET /tasks/{id}/report is not implemented. Owner: Agent B (DEC-06).",
  },
} satisfies Partial<Record<keyof SupportMap, { level: SupportMap[keyof SupportMap]; detail: string }>>;

interface IngestResponse {
  task_id: string;
  tf_files: Array<{ path: string; size_bytes: number }>;
  providers: Array<{ name: string; source?: string | null; version?: string | null }>;
  warnings: string[];
}

interface CheckResponse {
  task_id: string;
  runs: unknown[];
}

interface CaptureBody {
  task_id: string;
}

interface CaptureBodyResponse {
  task_id: string;
  available: boolean;
  plan_digest: string | null;
  captured_at: string | null;
  reason: string | null;
}

interface RequirementsResponse {
  requirements: unknown;
}

interface DirectCache {
  workspace: TaskWorkspace;
}

function hasSessionStorage(): boolean {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

function readCache(taskId: string): DirectCache | null {
  if (!hasSessionStorage()) return null;
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY_PREFIX + taskId);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DirectCache;
    if (!parsed || typeof parsed !== "object" || !parsed.workspace) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeCache(taskId: string, workspace: TaskWorkspace): void {
  if (!hasSessionStorage()) return;
  try {
    window.sessionStorage.setItem(CACHE_KEY_PREFIX + taskId, JSON.stringify({ workspace }));
  } catch {
    // Quota or serialization failures degrade to no cache; the next read fails closed.
  }
}

function requireCache(taskId: string): TaskWorkspace {
  const cache = readCache(taskId);
  if (!cache) {
    throw new ApiError(
      "not_supported",
      `No cached workspace for task ${taskId} in this browser session. ${NO_READ_MODEL_NOTE}`,
    );
  }
  return cache.workspace;
}

function deriveState(checks: CheckRun[]): TaskState {
  if (checks.length === 0) return "CREATED";
  return checks.every((check) => check.status === "Passed") ? "REVIEW_READY" : "CHECKING";
}

export interface DirectServiceOptions {
  workerUrl: string;
  aiUrl?: string | undefined;
  timeoutMs?: number;
}

export class DirectServiceClient implements PlanProofApi {
  readonly backend = WORKER_BACKEND;
  readonly support: SupportMap;

  private readonly workerUrl: string;
  private readonly aiUrl: string | undefined;
  private readonly timeoutMs: number | undefined;

  constructor(options: DirectServiceOptions) {
    this.workerUrl = options.workerUrl.replace(/\/$/, "");
    this.aiUrl = options.aiUrl?.replace(/\/$/, "") || undefined;
    this.timeoutMs = options.timeoutMs;
    this.support = {
      createTask: "available",
      getWorkspace: "available",
      runCheckSuite: "available",
      findings: "unavailable",
      extractRequirements: this.aiUrl ? "available" : "unavailable",
      generatePatch: "unavailable",
      planSummary: "unavailable",
      capturePlan: "available",
      approveTask: "unavailable",
      getEvidenceReport: "unavailable",
    };
  }

  private worker(path: string): string {
    return `${this.workerUrl}${path}`;
  }

  async createTask(input: CreateTaskInput): Promise<TaskRecord> {
    let ingest: IngestResponse;

    if (input.repo_source.kind === "zip") {
      const file = input.repo_source.file;
      if (!file) {
        throw new ApiError(
          "rejected",
          "A ZIP file is required for zip uploads. Choose an archive before creating the task.",
        );
      }
      const form = new FormData();
      form.append("file", file, file.name);
      ingest = await requestJson<IngestResponse>(this.worker("/ingest/upload"), {
        method: "POST",
        formData: form,
        timeoutMs: this.timeoutMs,
      });
    } else {
      ingest = await requestJson<IngestResponse>(this.worker("/ingest"), {
        method: "POST",
        body: { source_type: "git_url", git_url: input.repo_source.url },
        timeoutMs: this.timeoutMs,
      });
    }

    if (!ingest || typeof ingest.task_id !== "string" || !TASK_ID_PATTERN.test(ingest.task_id)) {
      throw new ApiError(
        "invalid_response",
        "The worker returned an ingest response that does not carry a 32-hex task id.",
      );
    }

    const now = new Date().toISOString();
    const task: TaskRecord = {
      task_id: ingest.task_id,
      state: "CREATED",
      goal: input.goal,
      mode: input.mode,
      created_at: now,
    };

    const summary: IngestSummary = {
      tf_files: Array.isArray(ingest.tf_files) ? ingest.tf_files : [],
      providers: Array.isArray(ingest.providers) ? ingest.providers : [],
      warnings: Array.isArray(ingest.warnings) ? ingest.warnings : [],
    };

    const workspace: TaskWorkspace = {
      task,
      requirements: [],
      checks: [],
      findings: [],
      baseline_findings: [],
      patch: null,
      plan_summary: null,
      approval: null,
      ingest: summary,
      plan_capture: null,
    };

    writeCache(task.task_id, workspace);
    return task;
  }

  getWorkspace(taskId: string): Promise<TaskWorkspace> {
    try {
      return Promise.resolve(requireCache(taskId));
    } catch (error) {
      return Promise.reject(error);
    }
  }

  async runCheckSuite(taskId: string): Promise<CheckSuiteResponse> {
    const workspace = requireCache(taskId);

    const response = await requestJson<CheckResponse>(this.worker("/check"), {
      method: "POST",
      body: { task_id: taskId, checks: [...MANDATORY_CHECKS] },
      timeoutMs: this.timeoutMs,
    });

    if (!response || !Array.isArray(response.runs) || !isCheckRunList(response.runs)) {
      throw new ApiError(
        "invalid_response",
        "The worker returned check runs that do not match contract checkrun.schema.json (or an empty suite).",
      );
    }

    const checks = response.runs as CheckRun[];
    const updated: TaskWorkspace = {
      ...workspace,
      checks,
      task: { ...workspace.task, state: deriveState(checks) },
    };
    writeCache(taskId, updated);

    return { checks, findings: updated.findings };
  }

  async extractRequirements(taskId: string, goal: string): Promise<Requirement[]> {
    const workspace = requireCache(taskId);
    if (!this.aiUrl) {
      throw new ApiError(
        "not_configured",
        "The AI service URL is not configured (set NEXT_PUBLIC_AI_URL to extract requirements).",
      );
    }

    const response = await requestJson<RequirementsResponse>(
      `${this.aiUrl}/tasks/${encodeURIComponent(taskId)}/requirements`,
      { method: "POST", body: { goal }, timeoutMs: this.timeoutMs },
    );

    if (!response || !isRequirementList(response.requirements)) {
      throw new ApiError(
        "invalid_response",
        "The AI service returned requirements that do not match contract requirement.schema.json.",
      );
    }

    const requirements = response.requirements as Requirement[];
    writeCache(taskId, { ...workspace, requirements });
    return requirements;
  }

  async capturePlan(taskId: string): Promise<PlanCapture> {
    const workspace = requireCache(taskId);

    const response = await requestJson<CaptureBodyResponse>(this.worker("/capture"), {
      method: "POST",
      body: { task_id: taskId } satisfies CaptureBody,
      timeoutMs: this.timeoutMs,
    });

    if (!response || typeof response.available !== "boolean") {
      throw new ApiError(
        "invalid_response",
        "The worker returned a capture response with an unexpected shape.",
      );
    }

    const capture: PlanCapture = response.available
      ? {
          available: true,
          plan_digest:
            typeof response.plan_digest === "string" &&
            DIGEST_PATTERN.test(response.plan_digest) &&
            response.plan_digest
              ? response.plan_digest
              : null,
          captured_at: response.captured_at ?? null,
          reason: null,
        }
      : { available: false, plan_digest: null, captured_at: null, reason: response.reason ?? "No plan was captured." };

    if (capture.available && !capture.plan_digest) {
      throw new ApiError(
        "invalid_response",
        "The worker reported a captured plan but did not return a 64-hex plan digest.",
      );
    }

    writeCache(taskId, { ...workspace, plan_capture: capture });
    return capture;
  }

  generatePatch(): Promise<PatchResponse> {
    return Promise.reject(
      new ApiError(
        "not_supported",
        "Patch generation is blocked: Agent C's /tasks/{id}/patch requires a server-resolved workspace path and the frontend must not send workspace paths (DEC-INT-04/05). Owner: Agent B (orchestration).",
      ),
    );
  }

  approveTask(): Promise<ApprovalResponse> {
    return Promise.reject(
      new ApiError(
        "not_supported",
        "Approval cannot be recorded: POST /tasks/{id}/approve is not implemented. Owner: Agent B (DEC-05).",
      ),
    );
  }

  getEvidenceReport(): Promise<EvidenceReport> {
    return Promise.reject(
      new ApiError(
        "not_supported",
        "The evidence report endpoint is not implemented (GET /tasks/{id}/report). Owner: Agent B (DEC-06). The in-page evidence summary remains available.",
      ),
    );
  }

  operationNotes() {
    const notes: Partial<Record<keyof SupportMap, { level: SupportMap[keyof SupportMap]; detail: string }>> = {
      ...NOTES,
    };
    notes.extractRequirements = this.aiUrl
      ? { level: "available", detail: `POST ${this.aiUrl}/tasks/{id}/requirements on the AI service.` }
      : { level: "unavailable", detail: "NEXT_PUBLIC_AI_URL is not configured." };
    return notes;
  }
}
