from __future__ import annotations

from aiokafka.admin import AIOKafkaAdminClient, NewTopic  # type: ignore[import-untyped]

from packages.contracts.topics import (
    TOPIC_AGENT_CARD,
    TOPIC_AUDIT,
    TOPIC_MESSAGE,
    TOPIC_SAMPLE,
    TOPIC_TASK_RESULT,
    endpoint_topic,
    processed_id_topic,
    topic_for,
)

__all__ = [
    "TOPIC_AUDIT",
    "TOPIC_MESSAGE",
    "TOPIC_SAMPLE",
    "TOPIC_AGENT_CARD",
    "TOPIC_TASK_RESULT",
    "endpoint_topic",
    "processed_id_topic",
]

_TICKET_CREATED = topic_for("support", "ticket", "created")

TOPIC_NAMES: dict[str, str] = {
    "agent.message.v1": TOPIC_MESSAGE,
    "agent.audit.v1": TOPIC_AUDIT,
    "agent.sample.v1": TOPIC_SAMPLE,
    # New-style event types: topic name == event type (environment-prefixed convention).
    _TICKET_CREATED: _TICKET_CREATED,
}

_ONE_DAY_MS = 86_400_000
_SEVEN_DAYS_MS = 7 * _ONE_DAY_MS

_CANONICAL_TOPICS: list[NewTopic] = [
    NewTopic(
        name=TOPIC_MESSAGE,
        num_partitions=1,
        replication_factor=1,
        topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)},
    ),
    NewTopic(
        name=TOPIC_AUDIT,
        num_partitions=1,
        replication_factor=1,
        topic_configs={"cleanup.policy": "compact"},
    ),
    NewTopic(
        name=TOPIC_SAMPLE,
        num_partitions=1,
        replication_factor=1,
        topic_configs={"retention.ms": str(_ONE_DAY_MS)},
    ),
    NewTopic(
        name=TOPIC_AGENT_CARD,
        num_partitions=1,
        replication_factor=1,
        topic_configs={"cleanup.policy": "compact"},
    ),
    NewTopic(
        name=TOPIC_TASK_RESULT,
        num_partitions=1,
        replication_factor=1,
        topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)},
    ),
]


async def create_topics(
    bootstrap_servers: str = "localhost:9092",
    extra_topics: list[NewTopic] | None = None,
) -> None:
    """Create canonical topics, ignoring errors for already-existing topics."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap_servers)
    await admin.start()
    try:
        topics = list(_CANONICAL_TOPICS)
        if extra_topics:
            topics.extend(extra_topics)
        await admin.create_topics(topics, validate_only=False)
    except Exception:
        pass
    finally:
        await admin.close()


def processed_id_new_topic(consumer_name: str) -> NewTopic:
    return NewTopic(
        name=processed_id_topic(consumer_name),
        num_partitions=1,
        replication_factor=1,
        topic_configs={"cleanup.policy": "compact"},
    )


def endpoint_topic_new_topic(agent_id: str) -> NewTopic:
    return NewTopic(
        name=endpoint_topic(agent_id),
        num_partitions=1,
        replication_factor=1,
        topic_configs={"retention.ms": str(_SEVEN_DAYS_MS)},
    )
