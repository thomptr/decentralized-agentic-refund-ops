# Contract: Configuration & Local Stack

Satisfies FR-009 (launch with standard command), FR-012 (toggle), SC-004 (zero extra setup steps),
and the US4 launch/stop scenarios.

## Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `AGENT_OBSERVABILITY_ENABLED` | `true` | master toggle (FR-012) |
| `LANGFUSE_PUBLIC_KEY` | — | LangFuse project public key |
| `LANGFUSE_SECRET_KEY` | — | LangFuse project secret key |
| `LANGFUSE_HOST` | SDK default | e.g. `http://localhost:3000` for local self-host |
| `AGENT_OBSERVABILITY_SAMPLE_RATE` | `1.0` | 0.0–1.0 trace sampling (high-volume edge case) |
| `AGENT_OBSERVABILITY_ENV` | `local` | LangFuse environment tag |
| `AGENT_OBSERVABILITY_EXPORTER` | `langfuse` | wired exporter; `cloudwatch`/`otlp` documented future values (FR-015) |
| `AGENT_HEARTBEAT_INTERVAL_S` | `10` | `system.agent.heartbeat` cadence; `0` disables |
| `REDACT_PII` (008, reused) | `true` | scrub prompts/completions before LangFuse export (FR-017) |
| `LOG_RAW_LLM_PROMPTS` (008, reused) | `false` | opt-in to send raw (un-redacted) prompts |
| `LOG_RAW_LLM_OUTPUTS` (008, reused) | `false` | opt-in to send raw (un-redacted) completions |

When `ENABLED=true` but keys are missing or `langfuse` is not installed ⇒ **no-op mode** (no error).
Documented in `infra/local/.env.langfuse.example`.

## LangFuse local stack — `infra/local/docker-compose.langfuse.yml`

Self-hosted v3 topology (separate file from the broker compose so the broker/agents run without it):

| Service | Role | Port (host) |
|---------|------|-------------|
| `langfuse-web` | UI + API (trace viewer, dashboards, prompts, evals) | `3000` |
| `langfuse-worker` | async ingestion/processing | internal |
| `postgres` | transactional store | internal |
| `clickhouse` | analytics store (traces/observations/scores) | internal |
| `redis` | queue/cache | internal |
| `minio` | S3-compatible blob store | internal (+ console optional) |

### Launch / stop contract (US4)

- **Up** (alongside broker): the standard startup path brings up this file too; trace viewer +
  dashboards reachable at `http://localhost:3000` (FR-009). First-run: create a project, copy
  public/secret keys into `.env.langfuse`, restart agents (documented in quickstart).
- **Down**: `docker compose -f infra/local/docker-compose.langfuse.yml down -v` stops all services
  with no orphaned state (US4-2).
- **Backend absent**: if this compose is not up, agents still process refund cases (FR-008/SC-006) —
  the SDK fails open.

## Startup wiring

- Each `apps/agents/*/main.py` calls `configure_observability()` once, beside `configure_logging()`
  (no handler edits — US3/SC-003).
- `infra/local/run-demo-agents.sh` optionally brings up the LangFuse compose and exports `LANGFUSE_*`
  so the three `uv run demo-*` agents register against local LangFuse.

## pyproject extra

`[observability]` optional extra: `langfuse` (v3). Transitive `opentelemetry-*`. Core install and the
default offline test suite do **not** require it.
