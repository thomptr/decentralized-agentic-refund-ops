README
# Decentralized Agentic Refund Operations

A proof-of-concept showing autonomous AI agents coordinating via Kafka events to handle end-to-end refund workflows — dispute intake, eligibility check, and payment reversal — without a central orchestrator.

This repository delivers the **event foundation**: the transport, contract, and audit layer that all future business agents build on. See the [quickstart guide](specs/001-event-foundation/quickstart.md) for a full end-to-end walkthrough.

## Quick start

```bash
# 1. Install dependencies
uv sync --extra dev   # or: pip install -e ".[dev]"

# 2. Start local Kafka (Redpanda) + UI
docker compose -f infra/local/docker-compose.yml up -d

# 3. Verify everything is healthy
python -m agent_foundation health

# 4. Publish a sample event (terminal B) and consume it (terminal A)
python -m agent_foundation consume-sample --consumer-group demo
python -m agent_foundation publish-sample --message "hello world"
```

Kafka UI is available at <http://localhost:8080>.

For the complete validation walkthrough (all five user stories), see [specs/001-event-foundation/quickstart.md](specs/001-event-foundation/quickstart.md).
