#!/usr/bin/env bash
# Launch all three demo agents for a one-command demo.
# Reuses the foundation's docker compose Kafka stack.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==> Starting Kafka (if not already running)..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

# ── LangFuse observability (Langfuse Cloud) ────────────────────────────────
# Traces export to the host configured in .env.langfuse (Langfuse Cloud). No
# local stack is started here; to self-host instead, bring up
# docker-compose.langfuse.yml manually and point LANGFUSE_HOST at it.
LANGFUSE_ENV_FILE="$SCRIPT_DIR/.env.langfuse"
if [ "${AGENT_OBSERVABILITY_ENABLED:-true}" != "false" ] && [ -f "$LANGFUSE_ENV_FILE" ]; then
  echo "==> Loading LangFuse env from .env.langfuse"
  # shellcheck disable=SC1090
  set -a; . "$LANGFUSE_ENV_FILE"; set +a
fi

echo "==> Waiting for broker to be ready..."
sleep 5

echo "==> Starting demo agents (press Ctrl-C to stop all)..."

# Launch the three agents in background subshells
cd "$PROJECT_ROOT"
# --extra observability installs the langfuse SDK the agents need to export
# traces; a plain `uv run` syncs only the default deps and would strip it out.
uv run --extra observability demo-billing-entitlement &
PID_BILLING=$!

uv run --extra observability demo-risk-fraud &
PID_RISK=$!

# Customer-resolution depends on billing being up — give it a moment
sleep 2
uv run --extra observability demo-customer-resolution &
PID_CUSTOMER=$!

echo ""
echo "  billing-entitlement-agent   (PID $PID_BILLING)"
echo "  risk-fraud-agent            (PID $PID_RISK)"
echo "  customer-resolution-agent   (PID $PID_CUSTOMER)"
echo ""
echo "  Discover agents:  uv run agent-foundation discover"
echo "  Submit a task:    uv run agent-foundation submit-task --target customer-resolution-agent --capability resolve_customer_case --text 'demo'"
echo ""
echo "Press Ctrl-C to stop all agents."

_cleanup() {
  kill "$PID_BILLING" "$PID_RISK" "$PID_CUSTOMER" 2>/dev/null || true
  exit 0
}
trap _cleanup INT TERM
wait
