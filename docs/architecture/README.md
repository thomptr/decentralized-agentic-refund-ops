# Architecture Documentation

This directory contains architecture documentation for the decentralized RefundOps system.
Documents here describe cross-cutting concerns and system-level design; agent-specific detail lives in
each agent's spec directory under `specs/`.

## Index

### Core workflow (feature 006)

| Document | Description |
|---|---|
| [decentralized-workflow.md](./decentralized-workflow.md) | End-to-end refund flow, four participants and their roles, non-refund path, happy-path sequence diagram |
| [event-choreography.md](./event-choreography.md) | Full topic topology table, how topic names resolve via `packages/contracts/topics.py` and `AGENT_ENVIRONMENT`, correlation/causation propagation rules, async result aggregation, causation DAG diagram |
| [replay-and-idempotency.md](./replay-and-idempotency.md) | Three idempotency layers (event / task / case), replay harness mechanism, why `decide()` purity makes replay deterministic |
| [failure-handling.md](./failure-handling.md) | Failure-mode → terminal-outcome table, timeout reaper enforcement loop, combined decision rule summary, config knobs (`CASE_DEADLINE_SECONDS`, `REAPER_TICK_SECONDS`) |
| [no-supervisor-verification.md](./no-supervisor-verification.md) | How absence of supervisor/router is proven (structural tests + audit trail), decentralization invariants, domain isolation, Constitution Principle I compliance |

### Foundational references (pre-006)

| Document | Description |
|---|---|
| [event-contracts.md](./event-contracts.md) | `EventEnvelope` field reference, root-event rule, payload registry, validation lifecycle |
| [topic-naming.md](./topic-naming.md) | Naming convention, canonical topic list, per-consumer processed-event topic, topic creation policy |
| [adding-new-agent.md](./adding-new-agent.md) | Step-by-step guide for adding a new agent: identity, payload, event type, registry, topic, handler, tests |

## Authoritative spec artifacts

For deeper detail, the canonical design artifacts live alongside the feature specs:

| Feature | Key artifacts |
|---|---|
| 001 event foundation | `specs/001-event-foundation/plan.md`, `contracts/` |
| 002 A2A runtime | `specs/002-a2a-runtime-contract/plan.md`, `contracts/` |
| 003 customer resolution | `specs/003-customer-resolution-agent/plan.md`, `contracts/decision-policy.md` |
| 004 billing entitlement | `specs/004-billing-entitlement-agent/plan.md` |
| 005 risk & fraud | `specs/005-risk-fraud-agent/plan.md` |
| 006 workflow choreography | `specs/006-workflow-choreography/spec.md`, `plan.md`, `contracts/` |
