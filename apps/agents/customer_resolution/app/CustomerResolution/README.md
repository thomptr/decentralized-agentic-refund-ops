# Customer Resolution Agent — AgentCore Code Package

This directory is the AgentCore `codeLocation` (CodeZip) for the Customer Resolution Agent.
`main.py` is the `serve_a2a` entrypoint; `pyproject.toml` declares the dev-venv dependencies.

All business logic (`ticket_classifier`, `decision_engine`, `response_drafter`, `models`) lives in
the monorepo and is imported from source via the `sys.path` wiring in `main.py`. The serve_a2a
executor delegates to `agentcore_app._invoke`, the same classify + decide pipeline the Kafka
entrypoint uses.

No new dependencies are declared here — all libraries were introduced by feature 004
(Billing Entitlement Agent) and are already used by the other agents' AgentCore packages.

See `agentcore/README.md` for full run instructions.
