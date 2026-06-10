# Contract: Timeout & Failure-Path Resolution (006)

Defines the **deterministic terminal outcome** for every failure mode (FR-017–FR-020, US3, SC-004,
SC-007). The decision rule itself is unchanged — see `decision-rule.md` and 003's
`contracts/decision-policy.md`. 006 makes the **timeout edge reachable at runtime** via the reaper and
proves each path resolves to a bounded terminal state.

## Failure-mode → terminal outcome table

| Trigger | Detected by | Terminal outcome | `escalation_reason` | FR / SC |
|---|---|---|---|---|
| Both peers silent past deadline | reaper sweep | `escalate_human` | `analysis_timeout` | FR-017, SC-004 |
| One peer silent past deadline | reaper sweep | `escalate_human` | `analysis_timeout` | FR-017, SC-004 |
| Peer returns `failed`/`rejected` `TaskResult` | `result_handler` → `mark_slot_failed` → `_apply_decision` | `escalate_human` | `peer_failure` | FR-018, SC-007 |
| Unparseable peer result | `result_handler` → `mark_slot_failed` | `escalate_human` | `peer_failure` | FR-018 |
| Delegation could not be sent (peer undiscoverable) | `intake_handler` except branch | `escalate_human` | `peer_failure` | FR-018 |
| Eligible **but** high/elevated risk (conflict) | `decision_engine` Row 8 / risk-result fast path | `escalate_human` | `conflicting_analyses` / `elevated_risk` | SC-007 |
| Peer requested human review | `decision_engine` Row 2 | `escalate_human` | `peer_requested_review` | SC-007 |
| Malformed / un-triageable ticket | `intake_handler` validation | `escalate_human` (never silently dropped) | `malformed_ticket` | FR-020 |
| Late opinion **after** terminal | `result_handler` late branch | recorded in audit, decision **unchanged** | — | FR-019 |

## Reaper behaviour (the new enforcement loop)

```
loop every REAPER_TICK_SECONDS until stop_event:
    now = clock()
    for case in store.list_timed_out_cases(now):          # non-terminal, past deadline, pending
        if case.status in {DECIDED} or is_terminal(case.status):   # re-check under guard
            continue
        ts = build_timeout_status(case, now)               # any_missing=True, deadline_exceeded=True
        _apply_decision(case, ...)                          # → escalate_human / analysis_timeout
```

Guarantees:
- **Bounded termination (SC-004)**: every case reaches terminal within `deadline + ≤ REAPER_TICK_SECONDS`
  grace.
- **No double decision (FR-013, FR-019)**: the reaper goes through the same `_apply_decision` DECIDED/
  terminal guard as the result loop; a case that received its last result just before the sweep is
  already (or becomes) DECIDED and is skipped.
- **No race on shared state**: `list_timed_out_cases` and all mutations run under the store's
  `asyncio.Lock`.
- **Determinism for tests/replay**: `clock` and `CASE_DEADLINE_SECONDS` are injectable; replay of a
  completed run neutralizes the reaper (research R2).

## Config
- `CASE_DEADLINE_SECONDS` (default e.g. `15`) — case deadline used by intake + reaper.
- `REAPER_TICK_SECONDS` (default e.g. `1.0`) — sweep cadence.
- Integration tests override both to sub-second values to exercise timeouts without waiting.

## Edge cases (spec §Edge Cases) — expected behaviour
- **Late opinion after timeout-escalation**: recorded in audit, does not flip/duplicate the terminal
  decision.
- **Duplicate final-decision attempt**: only one `customer.resolution.decided` emitted (case guard).
- **Both opinions missing**: `escalate_human` / `analysis_timeout`.
- **Replay of a partially-completed case**: reproduces the in-flight state; no spurious decision (reaper
  neutralized during completed-run replay; a stream with no decision yields no decision).
