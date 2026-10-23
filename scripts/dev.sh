#!/usr/bin/env bash
# One-command local development: worker (B) + ai (C) + audit (D) + Next.js.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export PLANPROOF_ROOT="$ROOT"
export PLANPROOF_DATA_DIR="${PLANPROOF_DATA_DIR:-$ROOT/data}"
export WORKER_DATA_DIR="${WORKER_DATA_DIR:-$ROOT/data/worker}"
export PLANPROOF_ORCHESTRATION_DIR="${PLANPROOF_ORCHESTRATION_DIR:-$ROOT/data/orchestration}"
export PLANPROOF_WORKER_URL="${PLANPROOF_WORKER_URL:-http://127.0.0.1:8081}"
export PLANPROOF_AI_URL="${PLANPROOF_AI_URL:-http://127.0.0.1:8082}"
export PLANPROOF_AUDIT_URL="${PLANPROOF_AUDIT_URL:-http://127.0.0.1:8083}"
export WORKER_PORT="${WORKER_PORT:-8081}"
export AI_PORT="${AI_PORT:-8082}"
export AUDIT_PORT="${AUDIT_PORT:-8083}"
export WEB_PORT="${WEB_PORT:-3000}"

# Explicit local-model defaults; never silently fall back to mock mode.
export MODEL_BACKEND="${MODEL_BACKEND:-ollama}"
export MODEL_MODE="${MODEL_MODE:-merged}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL_ID="${OLLAMA_MODEL_ID:-gemma4:e4b}"

PYTHON="${PLANPROOF_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "Python environment missing. Run: scripts/setup-local.sh" >&2
  exit 1
fi
if [[ ! -d web/node_modules ]]; then
  echo "Frontend dependencies missing. Run: scripts/setup-local.sh" >&2
  exit 1
fi

mkdir -p "$WORKER_DATA_DIR" "$PLANPROOF_ORCHESTRATION_DIR"

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$PYTHON" -m uvicorn worker.app.main:app --host 127.0.0.1 --port "$WORKER_PORT" &
pids+=("$!")
"$PYTHON" -m uvicorn planproof_ai.app:app --host 127.0.0.1 --port "$AI_PORT" &
pids+=("$!")
"$PYTHON" -m uvicorn services.audit_api.main:app --host 127.0.0.1 --port "$AUDIT_PORT" &
pids+=("$!")

wait_for() {
  local name="$1" url="$2" attempts=40
  for ((i = 0; i < attempts; i++)); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "$name ready"
      return 0
    fi
    sleep 0.5
  done
  echo "$name did not become ready at $url" >&2
  return 1
}

wait_for "worker" "$PLANPROOF_WORKER_URL/health" || exit 1
wait_for "ai" "$PLANPROOF_AI_URL/health" || exit 1
wait_for "audit" "$PLANPROOF_AUDIT_URL/health" || exit 1

echo "PlanProof UI: http://127.0.0.1:$WEB_PORT  (backend: $MODEL_BACKEND / $OLLAMA_MODEL_ID)"
npm --prefix web run dev -- --port "$WEB_PORT"
