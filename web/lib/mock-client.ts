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
import {
  DEMO_TASK_ID,
  buildEmptyWorkspace,
  demoChecks,
  demoPatch,
  demoRequirements,
  demoWorkspace,
  baselineFindings,
  currentFindings,
} from "./fixtures";
import { buildEvidenceReport } from "./report";

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class MockApiClient implements PlanProofApi {
  private readonly tasks = new Map<string, TaskWorkspace>();
  private sequence = 0;

  constructor() {
    this.tasks.set(DEMO_TASK_ID, clone(demoWorkspace));
  }

  async createTask(input: CreateTaskInput): Promise<TaskRecord> {
    await sleep(120);
    this.sequence += 1;
    const task: TaskRecord = {
      task_id: `task-${this.sequence}`,
      state: "CREATED",
      goal: input.goal,
      mode: input.mode,
      created_at: new Date().toISOString(),
    };
    this.tasks.set(task.task_id, buildEmptyWorkspace(task));
    return clone(task);
  }

  async getWorkspace(taskId: string): Promise<TaskWorkspace> {
    await sleep(80);
    const workspace = this.tasks.get(taskId);
    if (!workspace) {
      throw new ApiError(
        "not_found",
        `Task "${taskId}" was not found in the mock service.`,
      );
    }
    return clone(workspace);
  }

  async runCheckSuite(taskId: string): Promise<CheckSuiteResponse> {
    await sleep(200);
    const workspace = this.require(taskId);
    workspace.task = { ...workspace.task, state: "CHECKING" };
    workspace.checks = clone(demoChecks);
    workspace.findings = clone(currentFindings);
    workspace.baseline_findings =
      workspace.baseline_findings.length > 0
        ? workspace.baseline_findings
        : clone(baselineFindings);
    return {
      checks: clone(workspace.checks),
      findings: clone(workspace.findings),
    };
  }

  async generatePatch(taskId: string): Promise<PatchResponse> {
    await sleep(200);
    const workspace = this.require(taskId);
    workspace.task = { ...workspace.task, state: "PROPOSED" };
    workspace.patch = clone(demoPatch);
    if (workspace.requirements.length === 0) {
      workspace.requirements = clone(demoRequirements);
    }
    return { patch: clone(workspace.patch) };
  }

  async approveTask(
    taskId: string,
    planDigest: string,
  ): Promise<ApprovalResponse> {
    await sleep(120);
    const workspace = this.require(taskId);
    if (!workspace.plan_summary) {
      throw new ApiError(
        "not_found",
        "No plan has been captured for this task, so nothing can be approved.",
      );
    }
    if (workspace.plan_summary.plan_digest !== planDigest) {
      throw new ApiError(
        "invalid_response",
        "The plan digest no longer matches the captured plan. Approval was rejected.",
      );
    }
    const approvedAt = new Date().toISOString();
    workspace.approval = {
      approved_plan_digest: planDigest,
      approved_at: approvedAt,
    };
    return {
      task_id: taskId,
      approved_plan_digest: planDigest,
      approved_at: approvedAt,
    };
  }

  async getEvidenceReport(taskId: string): Promise<EvidenceReport> {
    await sleep(80);
    return buildEvidenceReport(this.require(taskId));
  }

  private require(taskId: string): TaskWorkspace {
    const workspace = this.tasks.get(taskId);
    if (!workspace) {
      throw new ApiError("not_found", `Task "${taskId}" was not found.`);
    }
    return workspace;
  }
}
