# AgentCore App Wrapper Deliverable — `agentcore_app.py`

> **Why this file exists**: `specs/005-risk-fraud-agent/tasks.md` was being rewritten by multiple
> concurrent sessions when this run executed, leaving it with duplicate task IDs and competing phase
> numbering. To avoid compounding that corruption (and to avoid having my edit clobbered by the next
> full-file rewrite), the `agentcore_app.py` wrapper tasks are captured here. **Merge this section into
> `tasks.md` once the parallel sessions have stopped**, using the next free IDs at that time (drafted
> below as T111/T112 against the max ID observed, T110 — re-check and renumber if the max has moved).

**Request**: *"Implement AgentCore app wrapper — create `apps/agents/risk_fraud/agentcore_app.py`.
Accept local AgentCore invocation payloads; parse into `RefundRiskAssessmentRequest`; run the risk
assessment service; return structured JSON; do not bypass A2A/Kafka contract tests. Acceptance:
AgentCore local invocation works; response includes risk level, recommendation, confidence, and
evidence; the AgentCore path is a demo/testing interface, not a supervisor."*

A `BedrockAgentCoreApp` `@app.entrypoint` that accepts a **local AgentCore invocation payload**, parses
it into `RiskAssessmentRequest` (alias `RefundRiskAssessmentRequest`, **T009**), runs the **existing**
`service.assess` unchanged (**T016**), and returns a structured JSON response. It is **distinct** from
the `serve_a2a` A2A server (`app/RiskFraud/main.py`, **T033** — JSON-RPC wire for the inspector) and the
FastAPI surface (`http_app.py`, **T032/T038**): this is a single-shot **dict-in / JSON-out demo/testing**
entrypoint for plain `agentcore` local invocation.

**Acceptance criteria → tasks**:
1. **AgentCore local invocation works** — the `@app.entrypoint` is invocable locally and returns a
   result (T112; asserted by T111).
2. **Response includes risk level, recommendation, confidence, and evidence** — the JSON carries
   `recommendation` (= `risk_level.value`), `confidence`, `evidence`, `reasoning_summary`,
   `requires_human_review`, and `policy_references` (T112; asserted by T111).
3. **Demo/testing interface, not a supervisor** — reuses `service.assess`, originates no `TaskRequest`,
   dispatches no work, makes no peer call, and publishes **nothing** to Kafka (that stays the Kafka
   entrypoint's job, **T020**), so it **does not bypass the A2A/Kafka contract tests** (**T032/T039**)
   (T112; asserted by T111 — no `Publisher`, no peer/runtime client; SC-008/FR-016).

> Depends only on US1 (`service.assess`, **T016**) + the Foundational input model (**T009**) —
> independent of US2/US5/US6 and of the `serve_a2a`/`http_app` shells, so it runs in parallel with them.

- [ ] T111 [P] [AC] **TDD** Write `apps/agents/risk_fraud/tests/test_agentcore_app.py` (failing first; **no broker**): invoking the `@app.entrypoint` in-process with a blocklist-customer payload returns `recommendation="high"` with a non-empty `evidence` set and ≥1 `fraud_policy` evidence item; a clean-customer payload returns `low`; a malformed payload returns a structured failure (reason, no fabricated verdict, FR-011); for the same input the entrypoint's verdict **equals** `service.assess` output (delegation proof); and the wrapper constructs **no** `Publisher` and **no** peer/runtime client and publishes nothing (demo/testing, not a supervisor — SC-008/FR-016).
- [ ] T112 [AC] Implement `apps/agents/risk_fraud/agentcore_app.py`: a `BedrockAgentCoreApp` with an `@app.entrypoint` `invoke(payload)` that (1) accepts a dict **or** JSON-string AgentCore payload, (2) parses it into `RiskAssessmentRequest` (T009) — on `ValueError` returns a structured error JSON with a reason, never a fabricated verdict (FR-011), (3) calls **`service.assess` unchanged** (T016), and (4) returns a JSON dict with `recommendation` (= `risk_level.value`), `confidence`, `evidence` (each item's `source`/`description`/`value`), `reasoning_summary`, `requires_human_review`, and `policy_references`; guard `if __name__ == "__main__": app.run()`. Add no peer call, no `TaskRequest`, no Kafka publish (FR-016). Make T111 pass.

**Checkpoint**: `agentcore_app.py` returns a structured risk verdict (risk level + recommendation +
confidence + evidence) from a local AgentCore invocation, reusing `service.assess`, and bypasses no
A2A/Kafka contract test.

---

## Note on overlap with the concurrently-added "Phase 12: AgentCore Local-Invocation Tests"

Another session added a **Phase 12: AgentCore Local-Invocation Tests** (tasks T042–T046 in its
numbering) that covers the same *functional intent* — accept a local payload, run `service.assess`,
return a structured data part, fail safely, and assert the path publishes nothing — but it routes that
behavior through the **existing** `app/RiskFraud/main.py` (`serve_a2a` executor) and `http_app.py`,
**not** through a dedicated `apps/agents/risk_fraud/agentcore_app.py` file. T111/T112 above add the
explicit `agentcore_app.py` `BedrockAgentCoreApp` entrypoint the request named. When merging, reconcile
the two: either (a) keep `agentcore_app.py` as the named local-invocation entrypoint and have it reuse
`service.assess` (recommended — it is the file the request asked for), or (b) if you adopt the Phase 12
routing instead, record that `agentcore_app.py` is intentionally folded into `app/RiskFraud/main.py` and
drop T112.
