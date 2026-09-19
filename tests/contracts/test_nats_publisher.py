"""
Validation tests for NATS Publisher.
Uses mocked NATS client to ensure zero infrastructure dependencies during testing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from intelligence.integration_bridge.nats_publisher import NATSPublisher


@pytest.fixture
def publisher() -> NATSPublisher:
    """Create a NATSPublisher instance for testing."""
    return NATSPublisher(nats_url="nats://mock:4222")


@pytest.mark.asyncio
async def test_connect_success(publisher: NATSPublisher) -> None:
    """Ensure successful NATS connection returns True."""
    mock_nc = AsyncMock()
    mock_nc.client_id = 12345

    with patch("nats.connect", new_callable=AsyncMock, return_value=mock_nc):
        result = await publisher.connect()

    assert result is True
    assert publisher._nc == mock_nc


@pytest.mark.asyncio
async def test_connect_failure_returns_false(publisher: NATSPublisher) -> None:
    """Ensure connection failure does not crash and returns False."""
    with patch("nats.connect", new_callable=AsyncMock, side_effect=OSError("refused")):
        result = await publisher.connect()

    assert result is False
    assert publisher._nc is None


@pytest.mark.asyncio
async def test_publish_success(publisher: NATSPublisher) -> None:
    """Ensure valid envelope bytes are published to correct topic."""
    mock_nc = AsyncMock()
    mock_nc.is_closed = False
    publisher._nc = mock_nc

    envelope = b'{"version":"1.0","payload":{}}'
    result = await publisher.publish(envelope, topic="atlas.control.decision.v1")

    assert result is True
    mock_nc.publish.assert_called_once_with("atlas.control.decision.v1", envelope)
    mock_nc.flush.assert_called_once()


@pytest.mark.asyncio
async def test_publish_skipped_when_disconnected(publisher: NATSPublisher) -> None:
    """Ensure publish returns False gracefully when not connected."""
    publisher._nc = None

    result = await publisher.publish(b'{"test": true}')

    assert result is False


@pytest.mark.asyncio
async def test_close_drains_connection(publisher: NATSPublisher) -> None:
    """Ensure graceful shutdown drains pending messages."""
    mock_nc = AsyncMock()
    mock_nc.is_closed = False
    publisher._nc = mock_nc

    await publisher.close()

    mock_nc.drain.assert_called_once()
