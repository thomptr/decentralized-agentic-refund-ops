"""Typer CLI for agent_foundation: health, publish-sample, consume-sample, etc."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import uuid
from datetime import UTC, datetime
from uuid import UUID

import typer

from agent_foundation.envelope import AgentIdentity, EventEnvelope
from agent_foundation.logging import configure_logging, get_logger

app = typer.Typer(name="agent-foundation", add_completion=False)


def _default_identity() -> AgentIdentity:
    return AgentIdentity(
        agent_id="cli.agent",
        display_name="CLI Agent",
        tenant_id="poc",
    )


@app.command()
def health(
    broker: str = typer.Option("localhost:9092", help="Kafka bootstrap server"),
) -> None:
    """Check broker connectivity and verify all canonical topics exist."""
    configure_logging()
    logger = get_logger("health")

    async def _run() -> bool:
        from aiokafka.admin import AIOKafkaAdminClient  # type: ignore[import-untyped]

        from agent_foundation.transport.topics import (
            TOPIC_AUDIT,
            TOPIC_MESSAGE,
            TOPIC_SAMPLE,
            create_topics,
        )

        expected = {TOPIC_MESSAGE, TOPIC_AUDIT, TOPIC_SAMPLE}
        ok = True

        admin = AIOKafkaAdminClient(bootstrap_servers=broker)
        try:
            await admin.start()
            meta = await admin.describe_cluster()  # type: ignore[attr-defined,unused-ignore]
            _ = meta
            logger.info("health.broker", broker=broker, status="ok")
        except Exception as exc:
            logger.error("health.broker", broker=broker, status="error", error=str(exc))
            ok = False
            return ok
        finally:
            with contextlib.suppress(Exception):
                await admin.close()

        # Ensure topics exist with correct configs.
        with contextlib.suppress(Exception):
            await create_topics(broker)

        admin2 = AIOKafkaAdminClient(bootstrap_servers=broker)
        try:
            await admin2.start()
            existing = set(await admin2.list_topics())
            missing = expected - existing
            found = len(expected) - len(missing)
            if missing:
                logger.warning(
                    "health.topics",
                    expected=len(expected),
                    found=found,
                    missing=sorted(missing),
                    status="degraded",
                )
                ok = False
            else:
                logger.info(
                    "health.topics",
                    expected=len(expected),
                    found=found,
                    status="ok",
                )
        except Exception as exc:
            logger.error("health.topics", error=str(exc), status="error")
            ok = False
        finally:
            with contextlib.suppress(Exception):
                await admin2.close()

        status = "ok" if ok else "error"
        logger.info("health.overall", status=status)
        return ok

    result = asyncio.run(_run())
    raise typer.Exit(0 if result else 1)


@app.command(name="publish-sample")
def publish_sample(
    message: str = typer.Option(..., help="Message body (1-200 chars)"),
    omit_causation: bool = typer.Option(False, "--omit-causation/--no-omit-causation"),
    non_root: bool = typer.Option(False, "--non-root/--no-non-root"),
    broker: str = typer.Option("localhost:9092"),
    correlation: str | None = typer.Option(None, help="Correlation UUID (generated if omitted)"),
) -> None:
    """Publish one agent.sample.v1 event."""
    configure_logging()

    async def _run() -> None:
        from agent_foundation.payloads.sample import SamplePayload
        from agent_foundation.transport.publisher import Publisher

        identity = _default_identity()
        corr_id = UUID(correlation) if correlation else uuid.uuid4()
        caus_id: UUID | None = None if omit_causation else uuid.uuid4()

        try:
            payload = SamplePayload(message=message)
        except Exception as exc:
            typer.echo(f"Payload validation failed: {exc}", err=True)
            raise typer.Exit(1) from exc

        if non_root and omit_causation:
            # Demonstrate missing-causation rejection path: write audit record and exit non-zero.
            from agent_foundation.audit.store import write_audit

            async with Publisher(identity, broker) as pub:
                partial = EventEnvelope.model_construct(
                    event_id=uuid.uuid4(),
                    correlation_id=corr_id,
                    causation_id=None,
                    agent_id=identity.agent_id,
                    tenant_id=identity.tenant_id,
                    timestamp=datetime.now(UTC),
                    event_type="agent.sample.v1",
                    schema_version="1.0.0",
                    payload=payload.model_dump(mode="json"),
                )
                await write_audit(pub, partial, "rejected", "missing_causation")
            typer.echo(
                "Rejected: missing_causation — audit record written to audit topic", err=True
            )
            raise typer.Exit(1)

        async with Publisher(identity, broker) as pub:
            try:
                envelope = await pub.publish(
                    payload=payload,
                    event_type="agent.sample.v1",
                    correlation_id=corr_id,
                    causation_id=caus_id,
                )
                typer.echo(f"Published event_id={envelope.event_id}")
            except Exception as exc:
                typer.echo(f"Publish failed: {exc}", err=True)
                raise typer.Exit(1) from exc

    asyncio.run(_run())


@app.command(name="consume-sample")
def consume_sample(
    consumer_group: str = typer.Option("demo", "--consumer-group"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Consume agent.sample.v1 events until Ctrl-C."""
    configure_logging()

    async def _run() -> None:
        from agent_foundation.transport.consumer import Consumer
        from agent_foundation.transport.topics import TOPIC_SAMPLE

        identity = _default_identity()

        async def handler(envelope: EventEnvelope) -> None:
            import json

            typer.echo(json.dumps(envelope.model_dump(mode="json"), default=str))

        consumer = Consumer(
            broker_url=broker,
            group_id=consumer_group,
            agent_identity=identity,
            idempotent=True,
        )
        consumer.subscribe([TOPIC_SAMPLE])
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def _sigint(*_: object) -> None:
            stop_event.set()

        loop.add_signal_handler(signal.SIGINT, _sigint)
        try:
            await consumer.run(handler, stop_event=stop_event)
        finally:
            await consumer.stop()

    asyncio.run(_run())


@app.command(name="publish-chain")
def publish_chain(
    length: int = typer.Option(3, "--length"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Publish N events as a causal chain; print shared correlation_id."""
    configure_logging()

    async def _run() -> None:
        from agent_foundation.payloads.sample import SamplePayload
        from agent_foundation.transport.publisher import Publisher

        identity = _default_identity()
        corr_id = uuid.uuid4()
        prev_id: UUID | None = None

        async with Publisher(identity, broker) as pub:
            for i in range(1, length + 1):
                payload = SamplePayload(message=f"chain event {i} of {length}")
                envelope = await pub.publish(
                    payload=payload,
                    event_type="agent.sample.v1",
                    correlation_id=corr_id,
                    causation_id=prev_id,
                )
                prev_id = envelope.event_id

        typer.echo(str(corr_id))

    asyncio.run(_run())


@app.command(name="query-audit")
def query_audit(
    correlation: str = typer.Option(..., "--correlation", help="Correlation UUID"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Print all audit records for the given correlation_id, in causal order."""
    configure_logging()

    async def _run() -> None:
        import json

        from agent_foundation.audit.store import query_by_correlation

        corr_id = UUID(correlation)
        records = await query_by_correlation(broker, corr_id)
        for rec in records:
            typer.echo(
                json.dumps(
                    {
                        "event_id": str(rec.original_envelope.event_id),
                        "causation_id": str(rec.original_envelope.causation_id),
                        "outcome": rec.outcome,
                        "recorded_at": rec.recorded_at.isoformat(),
                    }
                )
            )

    asyncio.run(_run())


@app.command()
def replay(
    topic: str = typer.Option(..., "--topic"),
    from_offset: str = typer.Option("earliest", "--from-offset"),
    consumer_group: str = typer.Option("replay", "--consumer-group"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Replay events from a chosen offset; idempotent consumers deduplicate automatically."""
    configure_logging()

    async def _run() -> None:
        import json

        from agent_foundation.transport.consumer import Consumer

        identity = _default_identity()

        async def handler(envelope: EventEnvelope) -> None:
            typer.echo(json.dumps(envelope.model_dump(mode="json"), default=str))

        consumer = Consumer(
            broker_url=broker,
            group_id=consumer_group,
            agent_identity=identity,
            idempotent=True,
        )
        consumer.subscribe([topic])

        if from_offset == "earliest":
            consumer.seek_to_beginning()
        elif from_offset == "latest":
            pass  # default
        else:
            consumer.seek_to_offset(int(from_offset))

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def _sigint(*_: object) -> None:
            stop_event.set()

        loop.add_signal_handler(signal.SIGINT, _sigint)
        try:
            await consumer.run(handler, stop_event=stop_event)
        finally:
            await consumer.stop()

    asyncio.run(_run())


@app.command(name="query-rejections")
def query_rejections(
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Print all rejected audit records."""
    configure_logging()

    async def _run() -> None:
        import json

        from agent_foundation.audit.store import consume_all_audit_records

        records = await consume_all_audit_records(broker)
        for rec in records:
            if rec.outcome == "rejected":
                typer.echo(
                    json.dumps(
                        {
                            "event_id": str(rec.original_envelope.event_id),
                            "reason": rec.reason,
                            "recorded_at": rec.recorded_at.isoformat(),
                        }
                    )
                )

    asyncio.run(_run())


@app.command(name="query-task-audit")
def query_task_audit(
    task_id: str = typer.Option(..., "--task-id", help="Task UUID"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """Print a task's full lifecycle from the audit topic, ordered by Kafka offset."""
    configure_logging()

    async def _run() -> None:
        import json

        from agent_foundation.audit.store import query_by_task_id

        tid = UUID(task_id)
        records = await query_by_task_id(broker, tid)
        if not records:
            typer.echo(f"No audit records found for task_id={task_id}", err=True)
            raise typer.Exit(1)
        for rec in records:
            typer.echo(
                json.dumps(
                    {
                        "event_id": str(rec.original_envelope.event_id),
                        "agent_id": rec.original_envelope.agent_id,
                        "outcome": rec.outcome,
                        "task_id": str(rec.task_id) if rec.task_id else None,
                        "reason": rec.reason,
                        "recorded_at": rec.recorded_at.isoformat(),
                    }
                )
            )

    asyncio.run(_run())


@app.command(name="discover")
def discover(
    capability: str | None = typer.Option(None, "--capability", help="Filter by capability id"),
    broker: str = typer.Option("localhost:9092"),
) -> None:
    """List discovered agents (optionally filtered by capability) from the card topic."""
    configure_logging()

    async def _run() -> None:
        import json

        from agent_foundation.runtime.discovery import discover_agents, find_capable

        cards = (
            await find_capable(capability, broker) if capability else await discover_agents(broker)
        )
        if not cards:
            typer.echo("No agent cards found.")
            return
        for card in sorted(cards, key=lambda c: c.agent_id):
            typer.echo(
                json.dumps(
                    {
                        "agent_id": card.agent_id,
                        "name": card.name,
                        "version": card.version,
                        "capabilities": [c.id for c in card.capabilities],
                        "security": card.security,
                    }
                )
            )

    asyncio.run(_run())


if __name__ == "__main__":
    app()
