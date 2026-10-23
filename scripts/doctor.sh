#!/usr/bin/env bash
# Diagnose the local PlanProof environment. Exit 1 on hard blockers.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

failures=0
warnings=0

pass() { printf 'PASS  %s\n' "$1"; }
warn() { printf 'WARN  %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

for cmd in node npm uv ollama git curl; do
  if command -v "$cmd" >/dev/null 2>&1; then pass "$cmd on PATH"; else fail "$cmd missing"; fi
done

if [[ -x .venv/bin/python ]]; then
  pass "python venv present"
  if .venv/bin/python -c "import fastapi, uvicorn, httpx, jsonschema" 2>/dev/null; then
    pass "python service dependencies importable"
  else
    fail "python dependencies missing (run scripts/setup-local.sh)"
  fi
  if .venv/bin/python -c "import planproof_ai" 2>/dev/null; then
    pass "ai package importable (editable install)"
  else
    fail "ai package not installed (uv pip install -e ai)"
  fi
  if .venv/bin/python -c "import audit" 2>/dev/null; then
    pass "audit package importable (repository root)"
  else
    fail "audit package not importable"
  fi
else
  fail ".venv missing (run scripts/setup-local.sh)"
fi

if [[ -d web/node_modules ]]; then pass "web dependencies installed"; else fail "web/node_modules missing (npm ci)"; fi

if curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  pass "ollama reachable at 127.0.0.1:11434"
  MODEL="${OLLAMA_MODEL_ID:-gemma4:e4b}"
  if curl -fsS --max-time 5 http://127.0.0.1:11434/api/tags | grep -q "\"$MODEL\""; then
    pass "model $MODEL present"
  else
    warn "model $MODEL not present (run: ollama pull $MODEL)"
  fi
else
  fail "ollama not reachable (start the Ollama app or: ollama serve)"
fi

if command -v terraform >/dev/null 2>&1; then
  pass "terraform: $(terraform version | head -n 1)"
else
  warn "terraform missing — checks will report UnableToVerify"
fi
if command -v checkov >/dev/null 2>&1; then
  pass "checkov: $(checkov --version 2>/dev/null)"
elif [[ -x .venv/bin/checkov ]]; then
  pass "checkov in .venv: $(.venv/bin/checkov --version 2>/dev/null)"
elif [[ -n "${PLANPROOF_CHECKOV_BIN:-}" ]]; then
  pass "checkov via PLANPROOF_CHECKOV_BIN"
else
  warn "checkov missing — findings will report UnableToVerify"
fi
if command -v opa >/dev/null 2>&1; then
  pass "opa: $(opa version 2>/dev/null | head -n 1)"
elif [[ -n "${PLANPROOF_OPA_BIN:-}" ]]; then
  pass "opa via PLANPROOF_OPA_BIN"
else
  warn "opa missing — policy findings will report UnableToVerify"
fi

if git rev-parse --verify 52649fa >/dev/null 2>&1; then
  if git diff --quiet 52649fa -- contracts 2>/dev/null; then
    pass "contracts/ unchanged since scaffold commit 52649fa"
  else
    fail "contracts/ differ from 52649fa"
  fi
else
  warn "scaffold commit 52649fa unavailable; contracts guard skipped"
fi

for url in "${PLANPROOF_WORKER_URL:-http://127.0.0.1:8081}" "${PLANPROOF_AI_URL:-http://127.0.0.1:8082}" "${PLANPROOF_AUDIT_URL:-http://127.0.0.1:8083}"; do
  if curl -fsS --max-time 2 "$url/health" >/dev/null 2>&1; then
    pass "service ready: $url"
  else
    warn "service not running: $url (scripts/dev.sh starts it)"
  fi
done

if [[ -f .env ]]; then pass ".env present"; else warn ".env missing (cp .env.example .env)"; fi

mkdir -p data 2>/dev/null && [[ -w data ]] && pass "data/ writable" || fail "data/ not writable"

echo
echo "Summary: $failures failure(s), $warnings warning(s)"
[[ "$failures" -eq 0 ]]
