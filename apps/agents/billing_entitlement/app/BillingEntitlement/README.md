# BillingEntitlement — AgentCore runtime entrypoint

`main.py` is the AWS AgentCore **A2A** entrypoint. It wraps the existing
`apps.agents.billing_entitlement.service.analyze` pipeline in an a2a-sdk
`AgentExecutor` and serves it via `bedrock_agentcore.runtime.serve_a2a`.

This is the `codeLocation` referenced by `../../agentcore/agentcore.json`. See
`../../agentcore/README.md` for how to run it locally with `agentcore dev`.
