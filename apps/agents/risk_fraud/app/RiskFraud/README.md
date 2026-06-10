# Risk Fraud Agent — AgentCore Code Package

This directory is the AgentCore `codeLocation` (CodeZip) for the Risk Fraud Agent.
`main.py` is the `serve_a2a` entrypoint; `pyproject.toml` declares the dev-venv dependencies.

All business logic (`service`, `scoring`, `mock_data`, `policy`, `models`) lives in the
monorepo and is imported from source via the `sys.path` wiring in `main.py`.

No new dependencies are declared here — all libraries were introduced by feature 004
(Billing Entitlement Agent) and are already present in the root project.

See `agentcore/README.md` for full run instructions.
