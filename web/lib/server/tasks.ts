import { execFile } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

import type { ApprovalRecord, IngestSummary, PlanCapture } from "../api";
import type {
  CheckRun,
  Finding,
  Patch,
  PlanSummary,
  Requirement,
  TaskMode,
  TaskState,
} from "../contracts";
import { serverConfig, MANDATORY_CHECKS } from "./config";
import { RequestError, UpstreamError, fetchJson } from "./upstream";
import {
  isValidTaskId,
  mutateTask,
  newTask,
  readTask,
  writeTask,
  type OrchestrationTask,
} from "./store";

const execFileAsync = promisify(execFile);

const INGEST_TIMEOUT_MS = 120_000;
const CHECK_TIMEOUT_MS = 600_000;
const FINDINGS_TIMEOUT_MS = 300_000;
const LLM_TIMEOUT_MS = 900_000;

interface WorkerIngestResponse {
  task_id: string;
  source_type: "zip" | "git_url";
  tf_files: Array<{ path: string; size_bytes: number }>;
  providers: Array<{ name: string; source?: string | null; version?: string | null }>;
  warnings: string[];
}

interface WorkerCheckResponse {
  task_id: string;
  runs: CheckRun[];
}

interface WorkerCaptureResponse {
  available: boolean;
  reason?: string | null;
  plan_digest?: string | null;
  captured_at?: string | null;
}

interface AuditDigestResponse {
  plan_digest: string;
}

interface AuditVerifyResponse {
  valid: boolean;
}

interface AuditClassifyResponse {
  plan_summary: PlanSummary;
}

interface AuditFindingsResponse {
  findings: Finding[];
}

interface AiRequirementsResponse {
  requirements: Requirement[];
}

interface AiPatchResponse {
  patch: Patch;
}

export interface TaskWorkspaceView {
  task: {
    task_id: string;
    state: TaskState;
    goal: string;
    mode: TaskMode;
    created_at: string;
    approval_valid: boolean | null;
  };
  requirements: Requirement[];
  checks: CheckRun[];
  findings: Finding[];
  baseline_findings: Finding[];
  patch: Patch | null;
  patch_applied_at: string | null;
  plan_summary: PlanSummary | null;
  approval: ApprovalRecord | null;
  ingest: IngestSummary | null;
  plan_capture: PlanCapture;
}

function toIngestSummary(response: WorkerIngestResponse): IngestSummary {
  return {
    tf_files: response.tf_files,
    providers: response.providers,
    warnings: response.warnings,
  };
}

export function workspacePath(taskId: string): string {
  if (!isValidTaskId(taskId)) throw new RequestError(400, "invalid_task_id", "invalid task id");
  return path.join(serverConfig.workerDataDir, taskId, "repo");
}

function planPath(taskId: string): string {
  return path.join(serverConfig.workerDataDir, taskId, "artifacts", "plan.raw.json");
}

async function readPlanJson(taskId: string): Promise<Record<string, unknown>> {
  const file = planPath(taskId);
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf-8");
  } catch {
    throw new RequestError(
      409,
      "plan_unavailable",
      "no captured plan JSON is available for this task; run checks and capture the plan first",
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new RequestError(422, "invalid_plan", "stored plan JSON is not valid JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new RequestError(422, "invalid_plan", "stored plan JSON is not an object");
  }
  return parsed as Record<string, unknown>;
}

async function runFindings(taskId: string): Promise<Finding[]> {
  const data = await fetchJson<AuditFindingsResponse>(
    `${serverConfig.auditUrl}/findings`,
    {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: FINDINGS_TIMEOUT_MS,
    },
  );
  return data.findings;
}

export async function createTaskFromUpload(input: {
  file: File;
  goal: string;
  mode: TaskMode;
}): Promise<TaskWorkspaceView> {
  const form = new FormData();
  form.set("file", input.file, input.file.name || "repo.zip");
  const response = await fetchJson<WorkerIngestResponse>(
    `${serverConfig.workerUrl}/ingest/upload`,
    { method: "POST", body: form, timeoutMs: INGEST_TIMEOUT_MS },
  );
  const task = newTask({
    taskId: response.task_id,
    goal: input.goal,
    mode: input.mode,
    ingest: toIngestSummary(response),
  });
  await writeTask(task);
  return taskView(task);
}

export async function createTaskFromGit(input: {
  url: string;
  goal: string;
  mode: TaskMode;
}): Promise<TaskWorkspaceView> {
  const response = await fetchJson<WorkerIngestResponse>(
    `${serverConfig.workerUrl}/ingest`,
    {
      method: "POST",
      body: JSON.stringify({ source_type: "git_url", git_url: input.url }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: INGEST_TIMEOUT_MS,
    },
  );
  const task = newTask({
    taskId: response.task_id,
    goal: input.goal,
    mode: input.mode,
    ingest: toIngestSummary(response),
  });
  await writeTask(task);
  return taskView(task);
}

export function taskView(task: OrchestrationTask): TaskWorkspaceView {
  return {
    task: {
      task_id: task.task_id,
      state: task.state,
      goal: task.goal,
      mode: task.mode,
      created_at: task.created_at,
      approval_valid: task.approval ? true : null,
    },
    requirements: task.requirements,
    checks: task.checks,
    findings: task.findings,
    baseline_findings: task.baseline_findings,
    patch: task.patch,
    patch_applied_at: task.patch_applied_at,
    plan_summary: task.plan_summary,
    approval: task.approval,
    ingest: task.ingest,
    plan_capture: task.plan_capture,
  };
}

export async function getWorkspace(taskId: string): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  return taskView(task);
}

export async function runChecks(taskId: string): Promise<TaskWorkspaceView> {
  const existing = await readTask(taskId);
  if (!existing) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");

  await mutateTask(taskId, (task) => {
    task.state = "CHECKING";
    task.events.push({ at: new Date().toISOString(), type: "checks_started" });
  });

  try {
    const response = await fetchJson<WorkerCheckResponse>(
      `${serverConfig.workerUrl}/check`,
      {
        method: "POST",
        body: JSON.stringify({ task_id: taskId, checks: MANDATORY_CHECKS }),
        headers: { "Content-Type": "application/json" },
        timeoutMs: CHECK_TIMEOUT_MS,
      },
    );
    const findings = await runFindings(taskId).catch((error: unknown) => {
      if (error instanceof UpstreamError) {
        throw new UpstreamError(
          error.status,
          error.code,
          `checks completed but findings could not be computed: ${error.message}`,
        );
      }
      throw error;
    });
    return await mutateTask(taskId, (task) => {
      task.checks = response.runs;
      task.findings = findings;
      if (task.patch_applied_at === null) task.baseline_findings = findings;
      task.state = "REVIEW_READY";
      task.events.push({
        at: new Date().toISOString(),
        type: "checks_completed",
        detail: `${response.runs.length} checks, ${findings.length} findings`,
      });
      return taskView(task);
    });
  } catch (error) {
    await mutateTask(taskId, (task) => {
      if (task.state === "CHECKING") task.state = "CREATED";
      task.events.push({
        at: new Date().toISOString(),
        type: "checks_failed",
        detail: error instanceof Error ? error.message : String(error),
      });
    }).catch(() => undefined);
    throw error;
  }
}

export async function extractRequirements(taskId: string): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  const response = await fetchJson<AiRequirementsResponse>(
    `${serverConfig.aiUrl}/tasks/${encodeURIComponent(taskId)}/requirements`,
    {
      method: "POST",
      body: JSON.stringify({ goal: task.goal }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: LLM_TIMEOUT_MS,
    },
  );
  return await mutateTask(taskId, (current) => {
    current.requirements = response.requirements;
    current.events.push({
      at: new Date().toISOString(),
      type: "requirements_extracted",
      detail: `${response.requirements.length} requirements`,
    });
    return taskView(current);
  });
}

export async function capturePlan(taskId: string): Promise<TaskWorkspaceView> {
  const existing = await readTask(taskId);
  if (!existing) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");

  const captured = await fetchJson<WorkerCaptureResponse>(
    `${serverConfig.workerUrl}/capture`,
    {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: CHECK_TIMEOUT_MS,
    },
  );
  if (!captured.available) {
    return await mutateTask(taskId, (task) => {
      task.plan_capture = {
        available: false,
        plan_digest: null,
        captured_at: null,
        reason: captured.reason ?? "plan capture was unavailable",
      };
      task.events.push({
        at: new Date().toISOString(),
        type: "plan_capture_unavailable",
        detail: captured.reason ?? undefined,
      });
      return taskView(task);
    });
  }

  const planJson = await readPlanJson(taskId);
  const [digest, classification] = await Promise.all([
    fetchJson<AuditDigestResponse>(`${serverConfig.auditUrl}/plan/digest`, {
      method: "POST",
      body: JSON.stringify({ plan_json: planJson }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: 60_000,
    }),
    fetchJson<AuditClassifyResponse>(`${serverConfig.auditUrl}/plan/classify`, {
      method: "POST",
      body: JSON.stringify({ plan_json: planJson }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: 60_000,
    }),
  ]);

  return await mutateTask(taskId, (task) => {
    task.plan_capture = {
      available: true,
      plan_digest: digest.plan_digest,
      captured_at: captured.captured_at ?? new Date().toISOString(),
      reason: null,
      worker_plan_digest: captured.plan_digest ?? null,
    };
    task.plan_summary = classification.plan_summary;
    task.approval = null;
    task.state = "AWAITING_APPROVAL";
    task.events.push({
      at: new Date().toISOString(),
      type: "plan_captured",
      detail: digest.plan_digest,
    });
    return taskView(task);
  });
}

export async function generatePatch(taskId: string): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  if (task.mode !== "build") {
    throw new RequestError(400, "bad_request", "patch generation requires build mode");
  }
  const diagnostics = task.checks
    .filter((check) => check.status === "Failed")
    .map((check) => `${check.check_id}: ${check.summary}`)
    .join("\n");
  const response = await fetchJson<AiPatchResponse>(
    `${serverConfig.aiUrl}/tasks/${encodeURIComponent(taskId)}/patch`,
    {
      method: "POST",
      body: JSON.stringify({
        workspace: workspacePath(taskId),
        goal: task.goal,
        requirements: task.requirements,
        diagnostics,
      }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: LLM_TIMEOUT_MS,
    },
  );
  return await mutateTask(taskId, (current) => {
    current.patch = response.patch;
    current.events.push({
      at: new Date().toISOString(),
      type: "patch_generated",
      detail: response.patch.patch_id,
    });
    return taskView(current);
  });
}

interface PatchApplyResult {
  applied: boolean;
  changed_paths: string[];
}

export async function applyPatch(taskId: string): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  if (!task.patch) throw new RequestError(400, "no_patch", "no generated patch to apply");
  if (task.patch_applied_at) {
    throw new RequestError(409, "patch_already_applied", "the patch has already been applied");
  }
  if (task.mode !== "build") {
    throw new RequestError(400, "bad_request", "patch application requires build mode");
  }

  const patchFile = path.join(
    serverConfig.orchestrationDir,
    `${taskId}.patch.json`,
  );
  await fs.writeFile(patchFile, JSON.stringify(task.patch), { mode: 0o600 });
  let result: PatchApplyResult;
  try {
    const { stdout } = await execFileAsync(
      serverConfig.pythonBin,
      [
        serverConfig.patchTool,
        "--workspace",
        workspacePath(taskId),
        "--allowed-root",
        serverConfig.workerDataDir,
        "--patch-file",
        patchFile,
      ],
      { timeout: 60_000 },
    );
    result = JSON.parse(stdout.trim()) as PatchApplyResult;
  } catch (error) {
    const withStderr = error as { stderr?: string; code?: number | string };
    const detail = (withStderr.stderr ?? "").trim() || String(error);
    if (withStderr.code === 3) {
      throw new RequestError(
        409,
        "stale_patch",
        "the workspace changed since the patch was generated; regenerate the patch",
      );
    }
    throw new RequestError(422, "patch_apply_failed", detail);
  } finally {
    await fs.unlink(patchFile).catch(() => undefined);
  }

  return await mutateTask(taskId, (current) => {
    current.patch_applied_at = new Date().toISOString();
    current.plan_capture = {
      available: false,
      plan_digest: null,
      captured_at: null,
      reason: "workspace changed after the patch was applied; re-run checks and capture the plan",
    };
    current.plan_summary = null;
    current.approval = null;
    current.state = "REVIEW_READY";
    current.events.push({
      at: new Date().toISOString(),
      type: "patch_applied",
      detail: result.changed_paths.join(", "),
    });
    return taskView(current);
  });
}

export async function approveTask(
  taskId: string,
  planDigest: string,
): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  if (task.state !== "AWAITING_APPROVAL" || !task.plan_capture.available) {
    throw new RequestError(
      409,
      "approval_not_ready",
      "approval requires a captured plan in the AWAITING_APPROVAL state",
    );
  }
  if (!task.plan_capture.plan_digest || task.plan_capture.plan_digest !== planDigest) {
    throw new RequestError(409, "digest_mismatch", "approval digest does not match the captured plan");
  }
  const planJson = await readPlanJson(taskId);
  const verified = await fetchJson<AuditVerifyResponse>(
    `${serverConfig.auditUrl}/plan/verify`,
    {
      method: "POST",
      body: JSON.stringify({ plan_json: planJson, expected: planDigest }),
      headers: { "Content-Type": "application/json" },
      timeoutMs: 60_000,
    },
  );
  if (!verified.valid) {
    throw new RequestError(
      409,
      "digest_mismatch",
      "the plan changed after capture; capture and review it again before approving",
    );
  }
  const approvedAt = new Date().toISOString();
  return await mutateTask(taskId, (current) => {
    current.approval = {
      approved_plan_digest: planDigest,
      approved_at: approvedAt,
    };
    current.state = "COMPLETE";
    current.events.push({
      at: approvedAt,
      type: "plan_approved",
      detail: planDigest,
    });
    return taskView(current);
  });
}

export async function refreshFindings(taskId: string): Promise<TaskWorkspaceView> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  const findings = await runFindings(taskId);
  return await mutateTask(taskId, (current) => {
    current.findings = findings;
    if (current.patch_applied_at === null && current.baseline_findings.length === 0) {
      current.baseline_findings = findings;
    }
    current.events.push({
      at: new Date().toISOString(),
      type: "findings_refreshed",
      detail: `${findings.length} findings`,
    });
    return taskView(current);
  });
}

interface ServiceHealth {
  reachable: boolean;
  health: Record<string, unknown> | null;
  capabilities: Record<string, unknown> | null;
  error?: string;
}

async function probeService(baseUrl: string): Promise<ServiceHealth> {
  try {
    const health = await fetchJson<Record<string, unknown>>(`${baseUrl}/health`, {
      timeoutMs: 5_000,
    });
    let capabilities: Record<string, unknown> | null = null;
    try {
      capabilities = await fetchJson<Record<string, unknown>>(
        `${baseUrl}/capabilities`,
        { timeoutMs: 10_000 },
      );
    } catch {
      capabilities = null;
    }
    return { reachable: true, health, capabilities };
  } catch (error) {
    return {
      reachable: false,
      health: null,
      capabilities: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function serviceCapabilities() {
  const [worker, ai, audit] = await Promise.all([
    probeService(serverConfig.workerUrl),
    probeService(serverConfig.aiUrl),
    probeService(serverConfig.auditUrl),
  ]);
  let ollama: { reachable: boolean; models: string[]; error?: string };
  try {
    const tags = await fetchJson<{ models?: Array<{ name?: string }> }>(
      `${serverConfig.ollamaUrl}/api/tags`,
      { timeoutMs: 5_000 },
    );
    ollama = {
      reachable: true,
      models: (tags.models ?? [])
        .map((model) => model.name ?? "")
        .filter((name) => name !== ""),
    };
  } catch (error) {
    ollama = {
      reachable: false,
      models: [],
      error: error instanceof Error ? error.message : String(error),
    };
  }
  return { worker, ai, audit, ollama };
}

export interface EvidenceReport {
  task_id: string;
  generated_at: string;
  state: TaskState;
  mode: TaskMode;
  goal: string;
  plan_digest: string | null;
  worker_plan_digest: string | null;
  approval: ApprovalRecord | null;
  tool_versions: Record<string, string | null>;
  checks: CheckRun[];
  findings: Finding[];
  baseline_findings: Finding[];
  requirements: Requirement[];
  plan_summary: PlanSummary | null;
  limitations: string[];
}

export async function buildReport(taskId: string): Promise<EvidenceReport> {
  const task = await readTask(taskId);
  if (!task) throw new RequestError(404, "TASK_NOT_FOUND", "task not found");
  const capabilities = await serviceCapabilities();
  const workerCaps = capabilities.worker.capabilities as
    | {
        tools?: Record<string, { version?: string | null }>;
      }
    | null;
  const auditCaps = capabilities.audit.capabilities as
    | {
        tools?: Record<string, { version?: string | null }>;
      }
    | null;
  const aiHealth = capabilities.ai.health as
    | { model_backend?: string; model_id?: string }
    | null;
  const limitations = new Set<string>(task.limitations);
  limitations.add("Terraform apply and cloud deployment are unavailable by design.");
  limitations.add("Approval is recorded locally for a single user; there is no remote identity provider.");
  if (task.patch && !task.patch_applied_at) {
    limitations.add("The generated patch has not been applied to the workspace.");
  }
  if (!task.plan_capture.available) {
    limitations.add("No plan digest is bound to this report yet.");
  }
  if (task.findings.some((finding) => finding.status === "UnableToVerify")) {
    limitations.add("Some findings are UnableToVerify and must not be read as passing.");
  }
  return {
    task_id: task.task_id,
    generated_at: new Date().toISOString(),
    state: task.state,
    mode: task.mode,
    goal: task.goal,
    plan_digest: task.plan_capture.plan_digest,
    worker_plan_digest: task.plan_capture.worker_plan_digest ?? null,
    approval: task.approval,
    tool_versions: {
      terraform: workerCaps?.tools?.terraform?.version ?? null,
      checkov: auditCaps?.tools?.checkov?.version ?? null,
      opa: auditCaps?.tools?.opa?.version ?? null,
      model_backend: aiHealth?.model_backend ?? null,
      model_id: aiHealth?.model_id ?? null,
    },
    checks: task.checks,
    findings: task.findings,
    baseline_findings: task.baseline_findings,
    requirements: task.requirements,
    plan_summary: task.plan_summary,
    limitations: [...limitations],
  };
}
