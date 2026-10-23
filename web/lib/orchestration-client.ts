import type {
  ApprovalResponse,
  CheckSuiteResponse,
  CreateTaskInput,
  EvidenceReport,
  PlanCapture,
  PlanProofApi,
  PatchResponse,
  SupportMap,
  TaskRecord,
  TaskWorkspace,
} from "./api";
import { ApiError } from "./api";
import type { Requirement } from "./contracts";
import { requestJson } from "./http";

const INGEST_TIMEOUT_MS = 180_000;
const CHECK_TIMEOUT_MS = 620_000;
const LLM_TIMEOUT_MS = 950_000;

const SUPPORT: SupportMap = {
  createTask: "available",
  getWorkspace: "available",
  runCheckSuite: "available",
  findings: "available",
  extractRequirements: "available",
  generatePatch: "available",
  planSummary: "available",
  capturePlan: "available",
  approveTask: "available",
  getEvidenceReport: "available",
};

interface WorkspaceView extends TaskWorkspace {
  patch_applied_at?: string | null;
}

/**
 * Same-origin client for the Next.js orchestration API. The browser only talks
 * to /api/*; credentials for worker/ai/audit services never leave the server.
 */
export class OrchestrationClient implements PlanProofApi {
  readonly backend = "orchestration" as const;
  readonly support = SUPPORT;
  private readonly baseUrl: string;

  constructor(baseUrl = "") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  async createTask(input: CreateTaskInput): Promise<TaskRecord> {
    const source = input.repo_source;
    if (source.kind === "zip") {
      if (!source.file) {
        throw new ApiError("rejected", "Choose a ZIP archive before creating a task.");
      }
      const form = new FormData();
      form.set("file", source.file, source.filename || "repo.zip");
      form.set("goal", input.goal);
      form.set("mode", input.mode);
      const view = await requestJson<WorkspaceView>(this.url("/api/tasks"), {
        method: "POST",
        formData: form,
        timeoutMs: INGEST_TIMEOUT_MS,
      });
      return view.task;
    }
    const view = await requestJson<WorkspaceView>(this.url("/api/tasks"), {
      method: "POST",
      body: {
        source_type: "git_url",
        git_url: source.url,
        goal: input.goal,
        mode: input.mode,
      },
      timeoutMs: INGEST_TIMEOUT_MS,
    });
    return view.task;
  }

  getWorkspace(taskId: string): Promise<TaskWorkspace> {
    return requestJson<WorkspaceView>(this.url(`/api/tasks/${taskId}`), {
      timeoutMs: 30_000,
    });
  }

  async runCheckSuite(taskId: string): Promise<CheckSuiteResponse> {
    const view = await requestJson<WorkspaceView>(
      this.url(`/api/tasks/${taskId}/check`),
      { method: "POST", timeoutMs: CHECK_TIMEOUT_MS },
    );
    return { checks: view.checks, findings: view.findings };
  }

  async approveTask(taskId: string, planDigest: string): Promise<ApprovalResponse> {
    const view = await requestJson<WorkspaceView>(
      this.url(`/api/tasks/${taskId}/approve`),
      { method: "POST", body: { plan_digest: planDigest }, timeoutMs: 120_000 },
    );
    if (!view.approval) {
      throw new ApiError("invalid_response", "the approval response did not record an approval");
    }
    return {
      task_id: view.task.task_id,
      approved_plan_digest: view.approval.approved_plan_digest,
      approved_at: view.approval.approved_at,
    };
  }

  getEvidenceReport(taskId: string): Promise<EvidenceReport> {
    return requestJson<EvidenceReport>(this.url(`/api/tasks/${taskId}/report`), {
      timeoutMs: 60_000,
    });
  }

  async generatePatch(taskId: string): Promise<PatchResponse> {
    const view = await requestJson<WorkspaceView>(
      this.url(`/api/tasks/${taskId}/patch`),
      { method: "POST", timeoutMs: LLM_TIMEOUT_MS },
    );
    if (!view.patch) {
      throw new ApiError("invalid_response", "the patch response did not include a patch");
    }
    return { patch: view.patch };
  }

  async extractRequirements(taskId: string, _goal: string): Promise<Requirement[]> {
    const view = await requestJson<WorkspaceView>(
      this.url(`/api/tasks/${taskId}/requirements`),
      { method: "POST", timeoutMs: LLM_TIMEOUT_MS },
    );
    return view.requirements;
  }

  async capturePlan(taskId: string): Promise<PlanCapture> {
    const view = await requestJson<WorkspaceView>(
      this.url(`/api/tasks/${taskId}/capture`),
      { method: "POST", timeoutMs: CHECK_TIMEOUT_MS },
    );
    return (
      view.plan_capture ?? {
        available: false,
        plan_digest: null,
        captured_at: null,
        reason: "the orchestration response omitted plan capture state",
      }
    );
  }

  async applyPatch(taskId: string): Promise<TaskWorkspace> {
    return requestJson<WorkspaceView>(this.url(`/api/tasks/${taskId}/patch/apply`), {
      method: "POST",
      timeoutMs: 120_000,
    });
  }
}
