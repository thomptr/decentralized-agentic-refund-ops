#!/usr/bin/env bash
# scripts/start-local-system.sh
# One-command demo: start Kafka + all three RefundOps agents.
#
# Usage:
#   bash scripts/start-local-system.sh               # start everything
#   bash scripts/start-local-system.sh --verify      # start + verify agent-card topics
#   bash scripts/start-local-system.sh --with-http   # start + expose HTTP surfaces
#   bash scripts/start-local-system.sh --help        # show help
#
# After starting:
#   uv run python apps/api/dev_publish_ticket.py      # inject a support ticket
#   uv run python apps/api/trace_case.py <correlation_id>  # trace the case

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source shared helpers
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
OPT_VERIFY=false
OPT_WITH_HTTP=false

for arg in "$@"; do
    case "${arg}" in
        --verify)
            OPT_VERIFY=true
            ;;
        --with-http)
            OPT_WITH_HTTP=true
            ;;
        --help|-h)
            cat <<'HELP'
start-local-system.sh — Start the RefundOps local demo stack

Usage:
  bash scripts/start-local-system.sh [OPTIONS]

Options:
  --verify      After launching, check that agent-card topics are present in Kafka.
  --with-http   Also start HTTP surfaces for billing (PORT=8101) and risk (A2A_ENDPOINT_PORT=8103) agents.
  --help, -h    Show this help message.

Environment variables (with defaults):
  AGENT_BROKER_URL=localhost:9092
  AGENT_ENVIRONMENT=local

Runtime state is written to .local-run/ (gitignored):
  .local-run/pids/<agent>.pid
  .local-run/logs/<agent>.log

To stop: bash scripts/stop-local-system.sh
HELP
            exit 0
            ;;
        *)
            log_err "Unknown option: ${arg}"
            log_err "Run with --help for usage."
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Change to project root so relative paths (.local-run/, etc.) work correctly
# ---------------------------------------------------------------------------
cd "${PROJECT_ROOT}"

# ---------------------------------------------------------------------------
# Create runtime state directories
# ---------------------------------------------------------------------------
mkdir -p "${LOCALRUN_PIDS}" "${LOCALRUN_LOGS}"

# ---------------------------------------------------------------------------
# Start infrastructure
# ---------------------------------------------------------------------------
log_info "Starting infrastructure (docker compose) ..."
docker compose -f infra/local/docker-compose.yml up -d

# ---------------------------------------------------------------------------
# Wait for Kafka to be ready
# ---------------------------------------------------------------------------
wait_for_kafka

# ---------------------------------------------------------------------------
# ensure_topics: create required Kafka topics via rpk
# Topics with auto-create enabled on the broker, but we create explicitly for
# correctness and so the trace/replay tools can rely on them existing.
# ---------------------------------------------------------------------------
ensure_topics() {
    if ! command -v rpk &>/dev/null; then
        log_warn "rpk not found — skipping explicit topic creation (auto-create is enabled on broker)."
        return 0
    fi

    log_info "Ensuring Kafka topics exist ..."

    # Collect topic names from contracts
    local topics
    topics="$(python - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "packages"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from contracts import topics as T
topic_vars = [v for k, v in vars(T).items()
              if isinstance(v, str) and not k.startswith("_") and k.isupper() and "TOPIC" in k]
for t in sorted(set(topic_vars)):
    print(t)
PYEOF
)"

    local broker="${AGENT_BROKER_URL:-localhost:9092}"
    while IFS= read -r topic; do
        if [[ -z "${topic}" ]]; then
            continue
        fi
        # Create with 1 partition, replication factor 1 (single-broker local)
        if rpk topic create "${topic}" \
               --brokers "${broker}" \
               --partitions 1 \
               --replicas 1 \
               &>/dev/null 2>&1; then
            log_info "  Topic created: ${topic}"
        else
            # Topic may already exist — that is fine
            log_info "  Topic already exists (or creation skipped): ${topic}"
        fi
    done <<<"${topics}"
}

ensure_topics

# ---------------------------------------------------------------------------
# Start the three agents as independent background processes (AC1: script
# exits immediately after launching — no wait, no loop, no supervisor).
# ---------------------------------------------------------------------------
log_info "Starting agents ..."

if "${OPT_WITH_HTTP}"; then
    log_info "  --with-http: adding HTTP surfaces (billing PORT=${BILLING_HTTP_PORT}, risk A2A_ENDPOINT_PORT=${RISK_HTTP_PORT})"
    # Billing entitlement with HTTP surface
    PORT="${BILLING_HTTP_PORT}" start_agent "billing-entitlement" \
        "PORT=${BILLING_HTTP_PORT} uv run demo-billing-entitlement-http"
    # Risk fraud with HTTP surface
    A2A_ENDPOINT_PORT="${RISK_HTTP_PORT}" start_agent "risk-fraud" \
        "A2A_ENDPOINT_PORT=${RISK_HTTP_PORT} uv run demo-risk-fraud-http"
else
    start_agent "billing-entitlement" "uv run demo-billing-entitlement"
    start_agent "risk-fraud" "uv run demo-risk-fraud"
fi

start_agent "customer-resolution" "uv run demo-customer-resolution"

# ---------------------------------------------------------------------------
# Optional --verify mode: check agent-card topics are present (T057)
# ---------------------------------------------------------------------------
if "${OPT_VERIFY}"; then
    log_info "Verifying agent-card topics are present ..."
    local_broker="${AGENT_BROKER_URL:-localhost:9092}"
    agent_card_topic="$(python - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "packages"))
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from contracts.topics import TOPIC_AGENT_CARD
print(TOPIC_AGENT_CARD)
PYEOF
)"
    if command -v rpk &>/dev/null; then
        if rpk topic describe "${agent_card_topic}" --brokers "${local_broker}" &>/dev/null 2>&1; then
            log_info "  Agent-card topic present: ${agent_card_topic}"
        else
            log_warn "  Agent-card topic not yet present: ${agent_card_topic} (agents may still be initialising)"
        fi
    else
        log_warn "  rpk not found — skipping agent-card topic verification."
    fi
fi

# ---------------------------------------------------------------------------
# AC1: Script exits here. No supervisor loop. Agents run independently.
# ---------------------------------------------------------------------------
log_info "---------------------------------------------------------------"
log_info "RefundOps local system started."
log_info ""
log_info "  billing-entitlement  PID $(cat "${LOCALRUN_PIDS}/billing-entitlement.pid" 2>/dev/null || echo '?')  log: ${LOCALRUN_LOGS}/billing-entitlement.log"
log_info "  risk-fraud           PID $(cat "${LOCALRUN_PIDS}/risk-fraud.pid" 2>/dev/null || echo '?')  log: ${LOCALRUN_LOGS}/risk-fraud.log"
log_info "  customer-resolution  PID $(cat "${LOCALRUN_PIDS}/customer-resolution.pid" 2>/dev/null || echo '?')  log: ${LOCALRUN_LOGS}/customer-resolution.log"
log_info ""
log_info "Next steps:"
log_info "  uv run python apps/api/dev_publish_ticket.py"
log_info "  uv run python apps/api/trace_case.py <correlation_id>"
log_info ""
log_info "To stop: bash scripts/stop-local-system.sh"
log_info "Kafka UI: http://localhost:${KAFKA_UI_PORT}"
log_info "---------------------------------------------------------------"
