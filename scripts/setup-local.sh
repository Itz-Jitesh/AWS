#!/usr/bin/env bash
# Reproducible local setup for macOS (Apple Silicon friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PULL_MODEL=1
for arg in "$@"; do
  case "$arg" in
    --skip-model) PULL_MODEL=0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

missing=0
for cmd in node npm uv ollama; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "MISSING: $cmd" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  echo "Install the missing tools, then re-run scripts/setup-local.sh" >&2
  exit 1
fi

echo "== Python environment (.venv) =="
if [[ ! -d .venv ]]; then
  uv venv .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt
uv pip install --python .venv/bin/python -e ai

echo "== Frontend dependencies =="
npm --prefix web ci --no-audit --no-fund

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "== Local model =="
if [[ "$PULL_MODEL" -eq 1 ]]; then
  MODEL="${OLLAMA_MODEL_ID:-gemma4:e4b}"
  if ollama list | awk '{print $1}' | grep -qx "$MODEL"; then
    echo "$MODEL already present"
  else
    echo "Pulling $MODEL (~6-10 GB, one time)..."
    ollama pull "$MODEL"
  fi
else
  echo "Skipped model pull (--skip-model). Run: ollama pull gemma4:e4b"
fi

echo "== Optional local tooling =="
for tool in terraform checkov opa; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "$tool: $(command -v "$tool")"
  else
    case "$tool" in
      terraform|opa) echo "MISSING: $tool — install with: brew install $tool" ;;
      checkov) echo "MISSING: checkov — install with: .venv/bin/pip install checkov==3.3.30" ;;
    esac
  fi
done

echo
echo "Setup complete. Next:"
echo "  1. scripts/doctor.sh"
echo "  2. scripts/dev.sh   (starts worker, ai, audit, and the Next.js UI)"
