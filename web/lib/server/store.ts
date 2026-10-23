import { promises as fs } from "node:fs";
import path from "node:path";

import type {
  ApprovalRecord,
  IngestSummary,
  PlanCapture,
} from "../api";
import type {
  CheckRun,
  Finding,
  Patch,
  PlanSummary,
  Requirement,
  TaskMode,
  TaskState,
} from "../contracts";
import { serverConfig, TASK_ID_RE } from "./config";

export interface TaskEvent {
  at: string;
  type: string;
  detail?: string;
}

export interface OrchestrationTask {
  schema_version: "1.0.0";
  task_id: string;
  goal: string;
  mode: TaskMode;
  created_at: string;
  updated_at: string;
  state: TaskState;
  ingest: IngestSummary | null;
  checks: CheckRun[];
  findings: Finding[];
  baseline_findings: Finding[];
  requirements: Requirement[];
  patch: Patch | null;
  patch_applied_at: string | null;
  plan_capture: PlanCapture & { worker_plan_digest?: string | null };
  plan_summary: PlanSummary | null;
  approval: ApprovalRecord | null;
  events: TaskEvent[];
  limitations: string[];
}

const locks = new Map<string, Promise<unknown>>();

export function isValidTaskId(taskId: string): boolean {
  return TASK_ID_RE.test(taskId);
}

function taskPath(taskId: string): string {
  return path.join(serverConfig.orchestrationDir, `${taskId}.json`);
}

async function ensureDir(): Promise<void> {
  await fs.mkdir(serverConfig.orchestrationDir, { recursive: true, mode: 0o700 });
}

export async function readTask(taskId: string): Promise<OrchestrationTask | null> {
  if (!isValidTaskId(taskId)) return null;
  try {
    const raw = await fs.readFile(taskPath(taskId), "utf-8");
    return JSON.parse(raw) as OrchestrationTask;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

export async function writeTask(task: OrchestrationTask): Promise<void> {
  if (!isValidTaskId(task.task_id)) throw new Error("invalid task id");
  await ensureDir();
  const target = taskPath(task.task_id);
  const tmp = `${target}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(tmp, `${JSON.stringify(task, null, 2)}\n`, { mode: 0o600 });
  await fs.rename(tmp, target);
}

async function withTaskLock<T>(taskId: string, fn: () => Promise<T>): Promise<T> {
  const previous = locks.get(taskId) ?? Promise.resolve();
  const next = previous.then(fn, fn);
  locks.set(
    taskId,
    next.catch(() => undefined),
  );
  try {
    return await next;
  } finally {
    if (locks.get(taskId) === next) locks.delete(taskId);
  }
}

export async function mutateTask<T = void>(
  taskId: string,
  mutate: (task: OrchestrationTask) => T | Promise<T>,
): Promise<T> {
  return withTaskLock(taskId, async () => {
    const task = await readTask(taskId);
    if (!task) throw new Error("task not found");
    const result = await mutate(task);
    task.updated_at = new Date().toISOString();
    await writeTask(task);
    return result;
  });
}

export function newTask(input: {
  taskId: string;
  goal: string;
  mode: TaskMode;
  ingest: IngestSummary | null;
}): OrchestrationTask {
  const now = new Date().toISOString();
  return {
    schema_version: "1.0.0",
    task_id: input.taskId,
    goal: input.goal,
    mode: input.mode,
    created_at: now,
    updated_at: now,
    state: "CREATED",
    ingest: input.ingest,
    checks: [],
    findings: [],
    baseline_findings: [],
    requirements: [],
    patch: null,
    patch_applied_at: null,
    plan_capture: {
      available: false,
      plan_digest: null,
      captured_at: null,
      reason: "plan not captured yet",
    },
    plan_summary: null,
    approval: null,
    events: [{ at: now, type: "task_created" }],
    limitations: [],
  };
}
