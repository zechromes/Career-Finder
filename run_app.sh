#!/usr/bin/env bash

# Start the Career Tracker API and Vue development server together.
set -euo pipefail

# Resolve paths relative to this script so it can be launched from any
# directory, for example with ./run_app.sh or /path/to/run_app.sh.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# Prefer the project's job-tracker conda environment, then the active `python`,
# so installed project dependencies such as pdfplumber and LangChain are available.
# Override with PYTHON_BIN when another interpreter should be used.
if [ -z "${PYTHON_BIN:-}" ]; then
  CONDA_ENV_PYTHON="${CONDA_EXE:+$(dirname "$(dirname "$CONDA_EXE")")/envs/job-tracker/bin/python}"
  if [ -n "$CONDA_ENV_PYTHON" ] && [ -x "$CONDA_ENV_PYTHON" ]; then
    PYTHON_BIN="$CONDA_ENV_PYTHON"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN="python3"
  fi
fi

# Check that the two tools needed to run the backend and frontend exist.
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: Python was not found. Set PYTHON_BIN to your Python executable."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Error: npm was not found. Install Node.js and npm first."
  exit 1
fi

# Install the FastAPI runtime dependencies in the selected Python environment
# when they are not already available.
if ! "$PYTHON_BIN" -c 'import fastapi, multipart, uvicorn, pandas, openpyxl, jobspy, apify_client, pdfplumber, langchain_chroma, langchain_openai' >/dev/null 2>&1; then
  echo "Installing FastAPI dependencies..."
  "$PYTHON_BIN" -m pip install -r "$PROJECT_DIR/backend/requirements.txt"
fi

# Install JavaScript dependencies automatically on the first run.
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# Only stop processes started by this launcher, including partial startup.
API_PID=""
VITE_PID=""
cleanup() {
  trap - EXIT INT TERM
  echo "Stopping Career Tracker..."
  for pid in "$API_PID" "$VITE_PID"; do
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Run the FastAPI API from the project root so it can import the existing
# pipeline modules and read the project's .env file.
echo "Starting FastAPI API at http://127.0.0.1:5000"
(cd "$PROJECT_DIR" && "$PYTHON_BIN" -m uvicorn backend.app:app --host 127.0.0.1 --port 5000) &
API_PID=$!

# Run Vite in development mode. Its proxy forwards /api requests to FastAPI.
echo "Starting Vue frontend at http://localhost:5173/"
(cd "$FRONTEND_DIR" && npm run dev -- --host localhost --strictPort) &
VITE_PID=$!

# Bash 3 (macOS) has no wait -n. Detect either child exiting so a failed
# backend cannot leave a frontend running with an unusable API proxy.
echo "Career Tracker started. Press Ctrl+C to stop both services."
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$VITE_PID" 2>/dev/null; do
  sleep 1
done
for pid in "$API_PID" "$VITE_PID"; do
  if ! kill -0 "$pid" 2>/dev/null; then
    code=0
    wait "$pid" || code=$?
    echo "A service stopped (exit $code); shutting down Career Tracker."
    [ "$code" -ne 0 ] || code=1
    exit "$code"
  fi
done
