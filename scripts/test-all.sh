#!/usr/bin/env bash
# Run every local test suite. Real-model and E2E checks are separate scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PLANPROOF_PYTHON:-$ROOT/.venv/bin/python}"

echo "== worker =="
(cd worker && "$PY" -m pytest)

echo "== ai =="
(cd ai && "$PY" -m pytest)

echo "== audit =="
(cd audit && "$PY" -m pytest)

echo "== web unit tests =="
npm --prefix web test

echo "== web typecheck =="
(cd web && npx next typegen >/dev/null && npx tsc --noEmit)

echo "== web production build =="
npm --prefix web run build

echo "All test suites completed."
