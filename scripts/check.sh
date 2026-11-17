#!/usr/bin/env bash
# Fail immediately if a verification stage fails or a required variable is missing.
set -euo pipefail
# Resolve the repository and selected Python environment independently of the caller’s directory.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Prefer the project's job-tracker conda environment, then the active Python.
if [ -z "${PYTHON_BIN:-}" ]; then
  CONDA_ENV_PYTHON="${CONDA_EXE:+$(dirname "$(dirname "$CONDA_EXE")")/envs/job-tracker/bin/python}"
  if [ -n "$CONDA_ENV_PYTHON" ] && [ -x "$CONDA_ENV_PYTHON" ]; then
    PYTHON_BIN="$CONDA_ENV_PYTHON"
  else
    PYTHON_BIN="python"
  fi
fi
# Accept only the optional browser-test switch.
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--e2e" ]; }; then
  echo "Usage: $0 [--e2e]" >&2
  exit 2
fi
cd "$PROJECT_DIR"
# Stop with one clear message instead of many import errors from the wrong environment.
if ! "$PYTHON_BIN" -c 'import sqlite3, jobspy, langchain_google_genai' >/dev/null 2>&1; then
  echo "Error: $PYTHON_BIN is missing project dependencies. Run 'conda activate job-tracker' or set PYTHON_BIN." >&2
  exit 1
fi
echo "Using Python: $PYTHON_BIN"
# Validate shell syntax and backend behavior before generating public API contracts.
bash -n run_app.sh scripts/check.sh
# Keep local tracing credentials from exporting synthetic test runs, and never
# send the live model availability check or HyDE ad generation from tests.
CAREER_LANGSMITH_TRACING=false CAREER_EVALUATION_PREFLIGHT=false QUERY_BUILDER=evidence "$PYTHON_BIN" -m unittest discover -s tests
# Regenerate frontend types from the authoritative FastAPI schema.
"$PYTHON_BIN" frontend/scripts/export_openapi.py
cd frontend
./node_modules/.bin/openapi-typescript openapi.json -o src/types/api.d.ts
# Run current and compatibility tests, then verify the production build.
npm test
npm run test:legacy
npm run build
# Browser workflows need the explicitly requested local test server.
if [ "${1:-}" = "--e2e" ]; then
  npm run test:e2e
fi
