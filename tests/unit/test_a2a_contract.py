"""Case 3: Client rejects unknown capability before sending task (T043).

T044 (client-side preflight) is the production implementation. This test validates
the UnsupportedCapability error contract and demonstrates the expected client behavior
once T044 is implemented.

No broker required.
"""

from __future__ import annotations

import pytest

from agent_foundation.runtime.errors import UnsupportedCapability


def test_unsupported_capability_error_shape() -> None:
    """UnsupportedCapability carries the right category and message."""
    exc = UnsupportedCapability("foo.cap")
    assert exc.category == "unsupported_capability"
    assert "foo.cap" in str(exc)
    assert isinstance(exc, Exception)


def test_case3_preflight_check_logic() -> None:
    """Simulate the T044 preflight: raise UnsupportedCapability before publish."""
    from agent_foundation.runtime.agent_card import AgentCard, Capability
    from packages.contracts.topics import endpoint_topic

    target_card = AgentCard(
        agent_id="target.agent",
        name="Target",
        description="Target agent",
        version="1.0.0",
        endpoint_topic=endpoint_topic("target.agent"),
        capabilities=[Capability(id="real.cap", name="Real Cap", description="desc")],
    )

    def _preflight(target_id: str, capability: str, cards: list[AgentCard]) -> None:
        """Preflight check: raises UnsupportedCapability if cap not declared on target card."""
        target = next((c for c in cards if c.agent_id == target_id), None)
        if target is not None:
            cap_ids = {cap.id for cap in target.capabilities}
            if capability not in cap_ids:
                raise UnsupportedCapability(capability)

    publish_called = False

    def _mock_publish() -> None:
        nonlocal publish_called
        publish_called = True

    # Should raise before publish
    with pytest.raises(UnsupportedCapability) as exc_info:
        _preflight("target.agent", "does.not.exist", [target_card])
        _mock_publish()

    assert not publish_called, "publish must not be called after preflight raises"
    assert exc_info.value.category == "unsupported_capability"
    assert "does.not.exist" in str(exc_info.value)
