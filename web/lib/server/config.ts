import path from "node:path";

function projectRoot(): string {
  if (process.env.PLANPROOF_ROOT) return path.resolve(process.env.PLANPROOF_ROOT);
  const cwd = process.cwd();
  if (path.basename(cwd) === "web") return path.dirname(cwd);
  return cwd;
}

const root = projectRoot();

function resolveFromRoot(value: string | undefined, fallback: string): string {
  return path.resolve(root, value && value.trim() !== "" ? value : fallback);
}

export const serverConfig = {
  root,
  workerUrl: (process.env.PLANPROOF_WORKER_URL ?? "http://127.0.0.1:8081").replace(/\/$/, ""),
  aiUrl: (process.env.PLANPROOF_AI_URL ?? "http://127.0.0.1:8082").replace(/\/$/, ""),
  auditUrl: (process.env.PLANPROOF_AUDIT_URL ?? "http://127.0.0.1:8083").replace(/\/$/, ""),
  ollamaUrl: (process.env.OLLAMA_BASE_URL ?? "http://127.0.0.1:11434").replace(/\/$/, ""),
  dataDir: resolveFromRoot(process.env.PLANPROOF_DATA_DIR, "data"),
  workerDataDir: resolveFromRoot(process.env.WORKER_DATA_DIR, "data/worker"),
  orchestrationDir: resolveFromRoot(
    process.env.PLANPROOF_ORCHESTRATION_DIR,
    "data/orchestration",
  ),
  pythonBin: resolveFromRoot(process.env.PLANPROOF_PYTHON, ".venv/bin/python"),
  patchTool: path.join(root, "scripts", "apply_patch.py"),
  modelBackend: process.env.MODEL_BACKEND ?? "",
  modelId: process.env.MODEL_ID ?? process.env.OLLAMA_MODEL_ID ?? "",
} as const;

export const TASK_ID_RE = /^[0-9a-f]{32}$/;

export const MANDATORY_CHECKS = ["fmt", "init", "validate", "plan", "show_json"] as const;
