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


def endpoint_topic(agent_id: str) -> str:
    return topic_for("agent", agent_id, "task.requested")
