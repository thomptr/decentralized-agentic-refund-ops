# Failure Handling

Authoritative source: `specs/006-workflow-choreography/contracts/timeout-and-failure-paths.md`.
Decision rule: `specs/006-workflow-choreography/contracts/decision-rule.md` and
`specs/003-customer-resolution-agent/contracts/decision-policy.md`.

## Failure-mode → terminal-outcome table

Every failure mode resolves to a **bounded terminal state**. No case remains open indefinitely (SC-004).

| Failure trigger | Detected by | Terminal outcome | `escalation_reason` | FR / SC |
|---|---|---|---|---|
| Both peers silent past deadline | Reaper sweep | `escalate_human` | `analysis_timeout` | FR-017, SC-004 |
| One peer silent past deadline | Reaper sweep | `escalate_human` | `analysis_timeout` | FR-017, SC-004 |
| Peer returns `failed` or `rejected` TaskResult | `result_handler` → `mark_slot_failed` → `_apply_decision` | `escalate_human` | `peer_failure` | FR-018, SC-007 |
| Unparseable peer result | `result_handler` → `mark_slot_failed` | `escalate_human` | `peer_failure` | FR-018 |
| Peer undiscoverable (delegation not sent) | `intake_handler` except branch | `escalate_human` | `peer_failure` | FR-018 |
| Eligible billing + high/elevated risk (conflict) | `decision_engine` Row 8 / risk-result fast path | `escalate_human` | `conflicting_analyses` | SC-007 |
| Ineligible billing + high risk | `decision_engine` Row 5 | `deny_refund` + separate risk/escalation flag | — | FR-024, SC-007 |
| Peer requested human review | `decision_engine` Row 2 | `escalate_human` | `peer_requested_review` | SC-007 |
| Malformed / un-triageable ticket | `intake_handler` validation | `escalate_human` (never silently dropped) | `malformed_ticket` | FR-020 |
| Late opinion after terminal decision | `result_handler` late branch | Decision **unchanged** (audit recorded) | — | FR-019 |

## Combined decision rule (summary)

The full truth table is in `specs/006-workflow-choreography/contracts/decision-rule.md`. First matching
row wins:

| Order | Condition | Outcome |
|---|---|---|
| 0 | Not a refund ticket | `direct_response` |
| 1 | Any opinion missing (timeout / never arrived) | `escalate_human` |
| 2 | Slot failed/rejected, or peer requests review | `escalate_human` |
| 3 | Combined confidence < 0.6 | `escalate_human` |
| 4 | Eligible + low risk | `approve_refund` |
| 5 | Ineligible + elevated/high risk | `deny_refund` (+ risk flag) |
| 6 | Partial eligibility + low/elevated risk | `offer_partial_credit` |
| 7 | Indeterminate billing | `request_more_information` |
| 8 | Residual conflict (eligible+high, ineligible+low) | `escalate_human` |

High or elevated risk **never auto-approves**. A missing or failed opinion **always escalates** rather
than deciding on partial information (spec Assumption "Aggregation policy").

## Timeout reaper (FR-017, SC-004)

The reaper is the only meaningful new agent logic in feature 006. It is an internal loop of the
Customer Resolution Agent — not a separate service or supervisor.

### Enforcement loop

```python
# apps/agents/customer_resolution/reaper.py (simplified)
async def run_reaper(store, clock, config, stop_event):
    while not stop_event.is_set():
        now = clock()
        for case in await store.list_timed_out_cases(now):
            if is_terminal(case.status):
                continue                       # already decided
            ts = build_timeout_status(case, now)   # any_missing=True, deadline_exceeded=True
            await _apply_decision(case, ts, ...)   # → escalate_human / analysis_timeout
        await asyncio.sleep(REAPER_TICK_SECONDS)
```

### Guarantees

- **Bounded termination**: every case reaches terminal within `CASE_DEADLINE_SECONDS + ≤ REAPER_TICK_SECONDS`.
- **No double decision** (FR-013, FR-019): the reaper routes through the same `_apply_decision`
  DECIDED/terminal guard as the result loop. A case that received its final result just before the
  sweep is already DECIDED and is skipped.
- **No race on shared state**: `list_timed_out_cases` and all mutations execute under the store's
  `asyncio.Lock`.
- **Injectable clock and config**: `clock` and `CASE_DEADLINE_SECONDS` are constructor parameters,
  enabling deterministic unit tests at sub-second intervals and neutralization for completed-run replay.

### Config knobs

| Variable | Default | Purpose |
|---|---|---|
| `CASE_DEADLINE_SECONDS` | `15` | Per-case deadline for collecting both opinions |
| `REAPER_TICK_SECONDS` | `1.0` | Sweep cadence |

Both are overridable via env vars and injectable in tests.

## Edge cases

- **Late opinion after timeout-escalation**: recorded in audit, does not flip or duplicate the terminal
  decision (FR-019).
- **Duplicate final-decision attempt**: only one `customer.resolution.decided` emitted — case guard
  prevents re-emission (FR-013).
- **Both opinions missing**: `escalate_human` / `analysis_timeout` (reaper fires after deadline).
- **Replay of partially-completed case**: reproduces the in-flight state without injecting a spurious
  decision (reaper neutralized for completed-run replay; a stream with no decision yields no decision).

## Related docs

- [replay-and-idempotency.md](./replay-and-idempotency.md) — idempotency layers including the DECIDED guard
- [decentralized-workflow.md](./decentralized-workflow.md) — happy-path flow
- [event-choreography.md](./event-choreography.md) — audit topic and causation chain
