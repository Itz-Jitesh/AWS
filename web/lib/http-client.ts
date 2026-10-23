import {
  ApiError,
  type ApprovalResponse,
  type CheckSuiteResponse,
  type CreateTaskInput,
  type EvidenceReport,
  type PatchResponse,
  type PlanProofApi,
  type TaskRecord,
  type TaskWorkspace,
} from "./api";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network", `Request to ${path} failed to reach the server.`);
  }

  if (response.status === 404) {
    throw new ApiError("not_found", `No resource at ${path}.`);
  }

  if (!response.ok) {
    throw new ApiError(
      "network",
      `Request to ${path} returned HTTP ${response.status}.`,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError("invalid_response", `Response from ${path} was not JSON.`);
  }
}

export class HttpApiClient implements PlanProofApi {
  constructor(private readonly baseUrl: string) {}

  private url(path: string): string {
    return `${this.baseUrl.replace(/\/$/, "")}${path}`;
  }

  createTask(input: CreateTaskInput): Promise<TaskRecord> {
    return requestJson<TaskRecord>(this.url("/tasks"), {
      method: "POST",
      body: JSON.stringify(input),
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
      {
        method: "POST",
        body: JSON.stringify({ plan_digest: planDigest }),
      },
    );
  }

  getEvidenceReport(taskId: string): Promise<EvidenceReport> {
    return requestJson<EvidenceReport>(
      this.url(`/tasks/${encodeURIComponent(taskId)}/report`),
    );
  }
}
