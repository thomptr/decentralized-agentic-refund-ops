#!/usr/bin/env bash
# scripts/lib/common.sh
# Shared helper library for local start/stop scripts.
# Source this file; do not execute it directly.
#
# One-command demo:
#   bash scripts/start-local-system.sh          # start infra + all three agents
#   uv run python apps/api/dev_publish_ticket.py # inject a ticket
#   uv run python apps/api/trace_case.py <id>    # trace the case
#   bash scripts/stop-local-system.sh            # tear down

set -euo pipefail

# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------
: "${AGENT_BROKER_URL:=localhost:9092}"
: "${AGENT_ENVIRONMENT:=local}"

# ---------------------------------------------------------------------------
# Runtime state directory convention
# ---------------------------------------------------------------------------
# All PID files and log files live under .local-run/ at the project root.
# .local-run/pids/<agent-name>.pid
# .local-run/logs/<agent-name>.log
LOCALRUN_DIR=".local-run"
LOCALRUN_PIDS="${LOCALRUN_DIR}/pids"
LOCALRUN_LOGS="${LOCALRUN_DIR}/logs"

# ---------------------------------------------------------------------------
# Port assignments
# ---------------------------------------------------------------------------
KAFKA_UI_PORT=8080
BILLING_HTTP_PORT=8101
RISK_HTTP_PORT=8103
DEMO_UI_PORT=8200

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info() {
    echo "[INFO]  $(date '+%H:%M:%S') $*"
}

log_warn() {
    echo "[WARN]  $(date '+%H:%M:%S') $*" >&2
}

log_err() {
    echo "[ERROR] $(date '+%H:%M:%S') $*" >&2
}

# ---------------------------------------------------------------------------
# wait_for_kafka
# Polls until the Kafka broker at AGENT_BROKER_URL is ready.
# Primary probe: rpk cluster health
# Fallback: raw TCP connection to port 9092
# ---------------------------------------------------------------------------
wait_for_kafka() {
    local broker="${AGENT_BROKER_URL:-localhost:9092}"
    local host="${broker%%:*}"
    local port="${broker##*:}"
    local max_attempts=30
    local attempt=0

    log_info "Waiting for Kafka broker at ${broker} ..."

    while (( attempt < max_attempts )); do
        attempt=$(( attempt + 1 ))

        # Primary: rpk cluster health
        if command -v rpk &>/dev/null; then
            if rpk cluster health --brokers "${broker}" &>/dev/null 2>&1; then
                log_info "Kafka is ready (rpk health check passed)."
                return 0
            fi
        fi

        # Fallback: TCP probe
        if command -v nc &>/dev/null; then
            if nc -z "${host}" "${port}" &>/dev/null 2>&1; then
                log_info "Kafka is ready (TCP probe ${host}:${port} succeeded)."
                return 0
            fi
        elif command -v bash &>/dev/null; then
            if bash -c "echo >/dev/tcp/${host}/${port}" &>/dev/null 2>&1; then
                log_info "Kafka is ready (bash TCP probe ${host}:${port} succeeded)."
                return 0
            fi
        fi

        log_info "  attempt ${attempt}/${max_attempts} — not ready yet, sleeping 2s ..."
        sleep 2
    done

    log_err "Kafka broker at ${broker} did not become ready after ${max_attempts} attempts."
    return 1
}

# ---------------------------------------------------------------------------
# start_agent <name> <command...>
# Runs <command> via nohup in the background.
# PID written to .local-run/pids/<name>.pid
# stdout+stderr redirected to .local-run/logs/<name>.log
# ---------------------------------------------------------------------------
start_agent() {
    local name="$1"
    shift
    local cmd="$*"
    local pidfile="${LOCALRUN_PIDS}/${name}.pid"
    local logfile="${LOCALRUN_LOGS}/${name}.log"

    # If already running, skip.
    if [[ -f "${pidfile}" ]]; then
        local existing_pid
        existing_pid="$(cat "${pidfile}")"
        if kill -0 "${existing_pid}" &>/dev/null 2>&1; then
            log_warn "Agent '${name}' is already running (PID ${existing_pid}). Skipping."
            return 0
        else
            log_warn "Stale pidfile for '${name}' (PID ${existing_pid} not found). Removing."
            rm -f "${pidfile}"
        fi
    fi

    log_info "Starting agent '${name}': ${cmd}"
    # shellcheck disable=SC2086
    nohup bash -c "${cmd}" >"${logfile}" 2>&1 &
    local pid=$!
    echo "${pid}" >"${pidfile}"
    log_info "  Agent '${name}' started (PID ${pid}), logging to ${logfile}"
}

# ---------------------------------------------------------------------------
# stop_agent <name>
# Reads PID from pidfile, sends SIGTERM, waits, SIGKILL fallback.
# Removes pidfile on completion. Idempotent if pidfile is missing.
# ---------------------------------------------------------------------------
stop_agent() {
    local name="$1"
    local pidfile="${LOCALRUN_PIDS}/${name}.pid"

    if [[ ! -f "${pidfile}" ]]; then
        log_info "No pidfile for '${name}' — already stopped or never started."
        return 0
    fi

    local pid
    pid="$(cat "${pidfile}")"

    if ! kill -0 "${pid}" &>/dev/null 2>&1; then
        log_info "Agent '${name}' (PID ${pid}) is not running — cleaning up pidfile."
        rm -f "${pidfile}"
        return 0
    fi

    log_info "Stopping agent '${name}' (PID ${pid}) ..."
    kill -TERM "${pid}" 2>/dev/null || true

    # Wait up to 10 seconds for graceful shutdown
    local waited=0
    while kill -0 "${pid}" &>/dev/null 2>&1 && (( waited < 10 )); do
        sleep 1
        waited=$(( waited + 1 ))
    done

    if kill -0 "${pid}" &>/dev/null 2>&1; then
        log_warn "Agent '${name}' (PID ${pid}) did not exit after ${waited}s — sending SIGKILL."
        kill -KILL "${pid}" 2>/dev/null || true
        sleep 1
    fi

    rm -f "${pidfile}"
    log_info "Agent '${name}' stopped."
}

# ---------------------------------------------------------------------------
# resolve_topics
# Prints each Kafka topic name defined in packages/contracts/topics.py
# by importing the module via Python.
# ---------------------------------------------------------------------------
resolve_topics() {
    python - <<'PYEOF'
import sys, os
# Ensure packages/ and src/ are importable
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(repo_root, "packages"))
sys.path.insert(0, os.path.join(repo_root, "src"))

from contracts import topics as T

topic_vars = [v for k, v in vars(T).items()
              if isinstance(v, str) and not k.startswith("_") and k.isupper() and "TOPIC" in k]
for t in sorted(set(topic_vars)):
    print(t)
PYEOF
}
