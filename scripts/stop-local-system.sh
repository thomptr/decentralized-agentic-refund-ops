#!/usr/bin/env bash
# scripts/stop-local-system.sh
# Stop the RefundOps local demo stack.
# Idempotent: tolerates missing pidfiles and already-stopped containers.
#
# Usage:
#   bash scripts/stop-local-system.sh               # stop agents + infra
#   bash scripts/stop-local-system.sh --keep-kafka  # stop agents only, leave Kafka running
#   bash scripts/stop-local-system.sh --status      # show current agent status
#   bash scripts/stop-local-system.sh --help        # show help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Source shared helpers
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
OPT_KEEP_KAFKA=false
OPT_STATUS=false

for arg in "$@"; do
    case "${arg}" in
        --keep-kafka)
            OPT_KEEP_KAFKA=true
            ;;
        --status)
            OPT_STATUS=true
            ;;
        --help|-h)
            cat <<'HELP'
stop-local-system.sh — Stop the RefundOps local demo stack

Usage:
  bash scripts/stop-local-system.sh [OPTIONS]

Options:
  --keep-kafka  Stop agents but leave Kafka/infrastructure running.
  --status      Show current agent status (PIDs + running/stopped).
  --help, -h    Show this help message.

The script is idempotent: it tolerates missing pidfiles and stopped containers.
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
# --status mode: report current state without changing anything
# ---------------------------------------------------------------------------
if "${OPT_STATUS}"; then
    log_info "Agent status:"
    for name in demo-ui customer-resolution risk-fraud billing-entitlement; do
        pidfile="${LOCALRUN_PIDS}/${name}.pid"
        if [[ -f "${pidfile}" ]]; then
            pid="$(cat "${pidfile}")"
            if kill -0 "${pid}" &>/dev/null 2>&1; then
                log_info "  ${name}: RUNNING (PID ${pid})"
            else
                log_info "  ${name}: STOPPED (stale pidfile, PID ${pid})"
            fi
        else
            log_info "  ${name}: STOPPED (no pidfile)"
        fi
    done
    exit 0
fi

# ---------------------------------------------------------------------------
# Stop agents in reverse start order
# ---------------------------------------------------------------------------
log_info "Stopping agents ..."
stop_agent "demo-ui"
stop_agent "customer-resolution"
stop_agent "risk-fraud"
stop_agent "billing-entitlement"

# ---------------------------------------------------------------------------
# Stop infrastructure (unless --keep-kafka)
# ---------------------------------------------------------------------------
if "${OPT_KEEP_KAFKA}"; then
    log_info "--keep-kafka: leaving Kafka/infrastructure running."
else
    log_info "Stopping infrastructure (docker compose) ..."
    # Tolerate compose not running (exit 0 even if containers are absent)
    docker compose -f infra/local/docker-compose.yml down \
        --remove-orphans \
        &>/dev/null 2>&1 || true
    log_info "Infrastructure stopped."
fi

log_info "Done."
