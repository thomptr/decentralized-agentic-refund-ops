from __future__ import annotations

import os


def resolve_topic(
    environment: str,
    domain: str,
    entity: str,
    action: str,
    version: str = "1",
) -> str:
    return f"{environment}.{domain}.{entity}.{action}.v{version}"


AGENT_ENVIRONMENT: str = os.environ.get("AGENT_ENVIRONMENT", "local")


def topic_for(
    domain: str,
    entity: str,
    action: str,
    version: str = "1",
    environment: str | None = None,
) -> str:
    env = environment if environment is not None else AGENT_ENVIRONMENT
    return resolve_topic(env, domain, entity, action, version)


def processed_id_topic(consumer_name: str) -> str:
    return f"{AGENT_ENVIRONMENT}.system.processed-id.{consumer_name}.recorded.v1"


TOPIC_AUDIT: str = topic_for("audit", "envelope", "recorded")
TOPIC_MESSAGE: str = topic_for("agent", "message", "sent")
TOPIC_SAMPLE: str = topic_for("system", "sample", "published")

TOPIC_AGENT_CARD: str = topic_for("agent", "agent-card", "published")
TOPIC_TASK_RESULT: str = topic_for("agent", "task", "result")

# Feature 003: Customer Resolution Agent topics
TOPIC_RESOLUTION_DECIDED: str = topic_for("customer", "resolution", "decided")
TOPIC_ISSUE_CLASSIFIED: str = topic_for("resolution", "customer-issue", "classified")
TOPIC_REFUND_REVIEW_REQUESTED: str = topic_for("resolution", "refund-review", "requested")
TOPIC_BILLING_RESULT: str = topic_for("billing", "refund-analysis", "completed")
TOPIC_RISK_RESULT: str = topic_for("risk", "review", "completed")
TOPIC_RESPONSE_DRAFTED: str = topic_for("resolution", "customer-response", "drafted")


def endpoint_topic(agent_id: str) -> str:
    return topic_for("agent", agent_id, "task.requested")
