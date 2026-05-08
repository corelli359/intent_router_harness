#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="${PYTHONPATH:-src}"
export INTENT_ROUTER_HARNESS_SPEC_PATH="${INTENT_ROUTER_HARNESS_SPEC_PATH:-examples/finance-router-harness.toml}"
export INTENT_ROUTER_HARNESS_REGRESSION_SUITE_PATH="${INTENT_ROUTER_HARNESS_REGRESSION_SUITE_PATH:-regressions/assistant_protocol_v0_6.json}"
export INTENT_ROUTER_HARNESS_LLM_ENV_FILE="${INTENT_ROUTER_HARNESS_LLM_ENV_FILE:-.env.local}"
export INTENT_ROUTER_HARNESS_LOG_LEVEL="${INTENT_ROUTER_HARNESS_LOG_LEVEL:-INFO}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8766}"

cmd=(
  python -m intent_router_harness
  serve-asgi
  --host "$HOST"
  --port "$PORT"
)

if [[ "${RELOAD:-0}" == "1" ]]; then
  cmd+=(--reload)
fi

echo "Starting intent_router_harness on http://127.0.0.1:${PORT}"
echo "Spec: ${INTENT_ROUTER_HARNESS_SPEC_PATH}"
echo "LLM env file: ${INTENT_ROUTER_HARNESS_LLM_ENV_FILE}"

exec "${cmd[@]}"
