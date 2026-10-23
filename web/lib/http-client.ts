import {
  ApiError,
  type ApprovalResponse,
  type BackendId,
  type CheckSuiteResponse,
  type CreateTaskInput,
  type EvidenceReport,
  type PatchResponse,
  type PlanProofApi,
  type SupportMap,
  type TaskRecord,
  type TaskWorkspace,
} from "./api";
import { requestJson } from "./http";

export const ORCHESTRATION_BACKEND: BackendId = "orchestration";

export const ORCHESTRATION_SUPPORT: SupportMap = {
  createTask: "unverified",
  getWorkspace: "unverified",
  runCheckSuite: "unverified",
  findings: "unverified",
  extractRequirements: "unavailable",
  generatePatch: "unverified",
  planSummary: "unverified",
  capturePlan: "unavailable",
  approveTask: "unverified",
  getEvidenceReport: "unverified",
};

const ORCHESTRATION_NOTE =
  "Proposed orchestration endpoint (E proposals, DEC-03/DEC-07). No service implements it yet — owner Agent B.";

export class HttpApiClient implements PlanProofApi {
  readonly backend = ORCHESTRATION_BACKEND;
  readonly support = ORCHESTRATION_SUPPORT;

  constructor(private readonly baseUrl: string) {}

  private url(path: string): string {
    return `${this.baseUrl.replace(/\/$/, "")}${path}`;
  }

  createTask(input: CreateTaskInput): Promise<TaskRecord> {
    const repoSource =
      input.repo_source.kind === "zip"
        ? { kind: "zip" as const, filename: input.repo_source.filename }
        : { kind: "git_url" as const, url: input.repo_source.url };
    return requestJson<TaskRecord>(this.url("/tasks"), {
      method: "POST",
      body: { repo_source: repoSource, goal: input.goal, mode: input.mode },
    });
  }

  getWorkspace(taskId: string): Promise<TaskWorkspace> {
    return requestJson<TaskWorkspace>(this.url(`/tasks/${encodeURIComponent(taskId)}`));
  }

  runCheckSuite(taskId: string): Promise<CheckSuiteResponse> {
    return requestJson<CheckSuiteResponse>(
      this.url(`/tasks/${encodeURIComponent(taskId)}/check`),
      { method: "POST" },
    );
  }

  generatePatch(taskId: string): Promise<PatchResponse> {
    return requestJson<PatchResponse>(
      this.url(`/tasks/${encodeURIComponent(taskId)}/patch`),
      { method: "POST" },
    );
  }

  approveTask(taskId: string, planDigest: string): Promise<ApprovalResponse> {
    return requestJson<ApprovalResponse>(
      this.url(`/tasks/${encodeURIComponent(taskId)}/approve`),
      { method: "POST", body: { plan_digest: planDigest } },
    );
  }

  getEvidenceReport(taskId: string): Promise<EvidenceReport> {
    return requestJson<EvidenceReport>(
      this.url(`/tasks/${encodeURIComponent(taskId)}/report`),
    );
  }

  operationNotes() {
    return {
      createTask: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      getWorkspace: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      runCheckSuite: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      generatePatch: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      approveTask: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      getEvidenceReport: { level: "unverified" as const, detail: ORCHESTRATION_NOTE },
      extractRequirements: {
        level: "unavailable" as const,
        detail:
          "No standalone requirements endpoint exists on the orchestration contract; requirements arrive in the task read model.",
      },
      capturePlan: {
        level: "unavailable" as const,
        detail: "Plan capture classification is not part of the proposed orchestration surface yet.",
      },
    };
  }
}

export function isUnsupported(error: unknown): boolean {
  return error instanceof ApiError && error.kind === "not_supported";
}
