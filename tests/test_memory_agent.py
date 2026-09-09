# MODULE: atlas-tests
# GOVERNANCE: Test suite for GovernedMemoryStore Python wrapper.
from __future__ import annotations

import time

import pytest

from intelligence.memory_agent.store import (
    CircuitState,
    GovernedMemoryStore,
    MemoryStoreError,
)
from intelligence.memory_agent.integration import (
    enrich_signal_from_memory,
    write_signal_to_memory,
)
from intelligence.research_agent.models import ForensicsSignal


def _make_store(**kwargs: object) -> GovernedMemoryStore:
    defaults: dict[str, object] = {
        "agent_id": "test-agent",
        "source_uri": "python-test://v1",
    }
    defaults.update(kwargs)
    return GovernedMemoryStore(**defaults)  # type: ignore[arg-type]


def _make_forensics(symbol: str = "BTCUSDT") -> ForensicsSignal:
    return ForensicsSignal(
        symbol=symbol, raw_spread_bps=10, aqs_score=80,
        confidence=0.85, orderbook_imbalance=0.5, vpin_toxicity=0.2,
        spoofing_detected=False, trace_id="t1",
        timestamp_ns=int(time.time() * 1e9),
        source_uri="rust-feature-engine://v1",
    )


class TestGovernedMemoryStore:
    def test_init_requires_agent_id(self) -> None:
        with pytest.raises(MemoryStoreError) as exc_info:
            GovernedMemoryStore(agent_id="", source_uri="t://v1")
        assert exc_info.value.code == "VAL_MISSING_AGENT_ID"
        assert exc_info.value.retryable is False

    def test_init_requires_source_uri(self) -> None:
        with pytest.raises(MemoryStoreError) as exc_info:
            GovernedMemoryStore(agent_id="a1", source_uri="")
        assert exc_info.value.code == "VAL_MISSING_SOURCE_BADGE"

    def test_write_and_read(self) -> None:
        store = _make_store()
        store.write_node("n1", "exchange", {"quality": "GOOD"})
        result = store.read_node("n1")
        assert result is not None
        assert result["node_id"] == "n1"
        assert result["attributes"]["quality"] == "GOOD"

    def test_write_without_source_rejected(self) -> None:
        store = _make_store()
        with pytest.raises(MemoryStoreError) as exc_info:
            store.write_node(
                "n1", "test", {}, override_source_uri=""
            )
        assert exc_info.value.code == "VAL_MISSING_SOURCE_BADGE"

    def test_write_without_agent_rejected(self) -> None:
        store = _make_store()
        with pytest.raises(MemoryStoreError) as exc_info:
            store.write_node(
                "n1", "test", {}, override_agent_id=""
            )
        assert exc_info.value.code == "VAL_MISSING_AGENT_ID"

    def test_write_empty_node_id_rejected(self) -> None:
        store = _make_store()
        with pytest.raises(MemoryStoreError) as exc_info:
            store.write_node("", "test", {})
        assert exc_info.value.code == "VAL_INVALID_NODE_ID"

    def test_read_nonexistent_returns_none(self) -> None:
        store = _make_store()
        assert store.read_node("missing") is None

    def test_ttl_expiry_raises_error(self) -> None:
        store = _make_store()
        store.write_node("n1", "test", {}, ttl_ns=1)  # 1ns TTL
        time.sleep(0.01)  # Wait for expiry
        with pytest.raises(MemoryStoreError) as exc_info:
            store.read_node("n1")
        assert exc_info.value.code == "VAL_TTL_EXPIRED"

    def test_cache_hit(self) -> None:
        store = _make_store()
        store.write_node("n1", "test", {"k": "v"})
        store.read_node("n1")  # First read = cache hit
        stats = store.stats
        assert stats["cache_hits"] == 1
        assert stats["reads"] == 1

    def test_search_keyword(self) -> None:
        store = _make_store()
        store.write_node("bybit_status", "exchange", {"quality": "DEGRADED"})
        store.write_node("binance_status", "exchange", {"quality": "GOOD"})
        results = store.search("degraded")
        assert len(results) == 1
        assert results[0]["node_id"] == "bybit_status"

    def test_search_case_insensitive(self) -> None:
        store = _make_store()
        store.write_node("n1", "Exchange", {"key": "Value"})
        assert len(store.search("exchange")) == 1
        assert len(store.search("VALUE")) == 1

    def test_circuit_breaker_opens_after_failures(self) -> None:
        store = _make_store(failure_threshold=3)
        assert store.circuit_state == CircuitState.CLOSED
        # Simulate failures by writing invalid data repeatedly
        for _ in range(3):
            with pytest.raises(MemoryStoreError):
                store.write_node("", "test", {})
        assert store.circuit_state == CircuitState.OPEN

    def test_circuit_breaker_blocks_when_open(self) -> None:
        store = _make_store(failure_threshold=1)
        with pytest.raises(MemoryStoreError):
            store.write_node("", "test", {})
        assert store.circuit_state == CircuitState.OPEN
        with pytest.raises(MemoryStoreError) as exc_info:
            store.write_node("n1", "test", {})
        assert exc_info.value.code == "DEP_STORE_UNAVAILABLE"
        assert exc_info.value.retryable is True

    def test_cache_eviction_on_max_size(self) -> None:
        store = _make_store(max_cache_size=3)
        for i in range(5):
            store.write_node(f"n{i}", "test", {})
        assert store.stats["cache_size"] <= 3

    def test_stats_tracking(self) -> None:
        store = _make_store()
        store.write_node("n1", "test", {})
        store.read_node("n1")
        store.read_node("missing")
        stats = store.stats
        assert stats["writes"] == 1
        assert stats["reads"] == 2
        assert stats["cache_hits"] == 1

    def test_source_uri_in_stored_node(self) -> None:
        store = _make_store(source_uri="python-market-analyst://v1")
        result = store.write_node("n1", "test", {})
        assert result["source_uri"] == "python-market-analyst://v1"

    def test_agent_id_in_stored_node(self) -> None:
        store = _make_store(agent_id="pricing-agent")
        result = store.write_node("n1", "test", {})
        assert result["agent_id"] == "pricing-agent"


class TestIntegration:
    def test_write_signal_to_memory(self) -> None:
        store = _make_store()
        sig = _make_forensics()
        result = write_signal_to_memory(store, sig)
        assert result is True

    def test_enrich_signal_from_memory(self) -> None:
        store = _make_store()
        sig = _make_forensics("ETHUSDT")
        write_signal_to_memory(store, sig)
        enriched = enrich_signal_from_memory(store, "ETHUSDT")
        assert enriched is not None
        assert enriched["count"] >= 1

    def test_enrich_missing_symbol_returns_none(self) -> None:
        store = _make_store()
        result = enrich_signal_from_memory(store, "NONEXISTENT")
        assert result is None


class TestRustIpcBridge:
    def test_find_binary_or_skip(self) -> None:
        from intelligence.memory_agent.bridge import _find_ipc_binary
        try:
            path = _find_ipc_binary()
            assert "ipc_server" in path
        except MemoryStoreError as e:
            assert e.code == "DEP_STORE_UNAVAILABLE"
            assert e.retryable is True

    def test_ipc_write_and_read(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        node_id = f"ipc_test_{int(time.time() * 1e9)}"
        try:
            bridge.write_node({
                "node_id": node_id, "entity_type": "test",
                "attributes": {"key": "value"},
                "source_uri": "python-test://v1", "agent_id": "test-agent",
                "ttl_ns": 0, "created_at_ns": 1, "updated_at_ns": 1,
            })
            result = bridge.read_node(node_id)
            assert result is not None
            assert result["node_id"] == node_id
        finally:
            bridge.stop()

    def test_ipc_search(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        node_id = f"search_{int(time.time() * 1e9)}"
        try:
            bridge.write_node({
                "node_id": node_id, "entity_type": "exchange",
                "attributes": {"quality": "DEGRADED_UNIQUE"},
                "source_uri": "python-test://v1", "agent_id": "test-agent",
                "ttl_ns": 0, "created_at_ns": 1, "updated_at_ns": 1,
            })
            results = bridge.search("DEGRADED_UNIQUE")
            assert any(r["node_id"] == node_id for r in results)
        finally:
            bridge.stop()

    def test_ipc_stats(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            stats = bridge.stats()
            assert "total_nodes" in stats
        finally:
            bridge.stop()

    def test_ipc_missing_source_rejected(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            with pytest.raises(MemoryStoreError):
                bridge.write_node({
                    "node_id": "bad", "entity_type": "test",
                    "attributes": {}, "source_uri": "",
                    "agent_id": "a1", "ttl_ns": 0,
                    "created_at_ns": 1, "updated_at_ns": 1,
                })
        finally:
            bridge.stop()


class TestIntegrationHelpers:
    def test_get_exchange_quality_empty(self) -> None:
        from intelligence.memory_agent.integration import get_exchange_quality
        store = _make_store()
        assert get_exchange_quality(store, "bybit") is None

    def test_set_and_get_exchange_quality(self) -> None:
        from intelligence.memory_agent.integration import (
            get_exchange_quality, set_exchange_quality,
        )
        store = _make_store()
        assert set_exchange_quality(store, "Bybit", "DEGRADED") is True
        assert get_exchange_quality(store, "bybit") == "DEGRADED"


class TestAgentSelfAudit:
    def test_record_and_search_lesson(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        assert audit.record_lesson(
            agent_id="analyst",
            decision_node_id="dec_001",
            lesson="Never ignore spoofing with confidence > 0.8",
            context={"signal": "sig_001"},
        ) is True
        lessons = audit.search_lessons("spoofing")
        assert len(lessons) >= 1
        assert "spoofing" in lessons[0]["attributes"]["lesson"]

    def test_audit_decision_loss(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        store.write_node(
            node_id="dec_loss_1",
            entity_type="decision",
            attributes={"action": "HOLD"},
            ttl_ns=0,
        )
        lesson = audit.audit_decision("dec_loss_1", "loss", "analyst")
        assert lesson is not None
        assert "loss" in lesson

    def test_audit_decision_win_returns_none(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        store.write_node(
            node_id="dec_win_1",
            entity_type="decision",
            attributes={"action": "SELL"},
            ttl_ns=0,
        )
        lesson = audit.audit_decision("dec_win_1", "win", "analyst")
        assert lesson is None


class TestIpcReplayCommands:
    def test_ipc_replay_at(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            bridge.write_node({
                "node_id": "replay_test", "entity_type": "test",
                "attributes": {}, "source_uri": "t://v1", "agent_id": "a1",
                "ttl_ns": 0, "created_at_ns": 100, "updated_at_ns": 100,
            })
            client = IpcReplayClient(bridge)
            result = client.replay_at(200)
            assert "nodes" in result
            assert any(n["node_id"] == "replay_test" for n in result["nodes"])
        finally:
            bridge.stop()

    def test_ipc_causal_trace(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            bridge.write_node({
                "node_id": "trace_root", "entity_type": "signal",
                "attributes": {}, "source_uri": "t://v1", "agent_id": "a1",
                "ttl_ns": 0, "created_at_ns": 100, "updated_at_ns": 100,
            })
            client = IpcReplayClient(bridge)
            chain = client.causal_trace("trace_root")
            assert isinstance(chain, list)
            assert len(chain) >= 1
        finally:
            bridge.stop()

    def test_ipc_diff(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            client = IpcReplayClient(bridge)
            result = client.diff(100, 200)
            assert "added" in result
            assert "removed" in result
        finally:
            bridge.stop()


class TestAgentSelfAudit:
    def test_record_and_search_lesson(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        assert audit.record_lesson(
            agent_id="analyst",
            decision_node_id="dec_001",
            lesson="Never ignore spoofing with confidence > 0.8",
            context={"signal": "sig_001"},
        ) is True
        lessons = audit.search_lessons("spoofing")
        assert len(lessons) >= 1
        assert "spoofing" in lessons[0]["attributes"]["lesson"]

    def test_audit_decision_loss(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        store.write_node(
            node_id="dec_loss_1",
            entity_type="decision",
            attributes={"action": "HOLD"},
            ttl_ns=0,
        )
        lesson = audit.audit_decision("dec_loss_1", "loss", "analyst")
        assert lesson is not None
        assert "loss" in lesson

    def test_audit_decision_win_returns_none(self) -> None:
        from intelligence.memory_agent.replay import AgentSelfAudit
        store = _make_store()
        audit = AgentSelfAudit(store)
        store.write_node(
            node_id="dec_win_1",
            entity_type="decision",
            attributes={"action": "SELL"},
            ttl_ns=0,
        )
        lesson = audit.audit_decision("dec_win_1", "win", "analyst")
        assert lesson is None


class TestIpcReplayCommands:
    def test_ipc_replay_at(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            bridge.write_node({
                "node_id": "replay_test", "entity_type": "test",
                "attributes": {}, "source_uri": "t://v1", "agent_id": "a1",
                "ttl_ns": 0, "created_at_ns": 100, "updated_at_ns": 100,
            })
            client = IpcReplayClient(bridge)
            result = client.replay_at(200)
            assert "nodes" in result
            assert any(n["node_id"] == "replay_test" for n in result["nodes"])
        finally:
            bridge.stop()

    def test_ipc_causal_trace(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            bridge.write_node({
                "node_id": "trace_root", "entity_type": "signal",
                "attributes": {}, "source_uri": "t://v1", "agent_id": "a1",
                "ttl_ns": 0, "created_at_ns": 100, "updated_at_ns": 100,
            })
            client = IpcReplayClient(bridge)
            chain = client.causal_trace("trace_root")
            assert isinstance(chain, list)
            assert len(chain) >= 1
        finally:
            bridge.stop()

    def test_ipc_diff(self) -> None:
        from intelligence.memory_agent.bridge import RustIpcBridge, _find_ipc_binary
        from intelligence.memory_agent.replay import IpcReplayClient
        try:
            _find_ipc_binary()
        except MemoryStoreError:
            pytest.skip("Rust IPC binary not built")
        bridge = RustIpcBridge(response_timeout_secs=2.0)
        try:
            client = IpcReplayClient(bridge)
            result = client.diff(100, 200)
            assert "added" in result
            assert "removed" in result
        finally:
            bridge.stop()


class TestProtocol:
    def test_signal_node_creation(self) -> None:
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority, SignalStatus,
        )
        sig = SignalNode(
            signal_id="sig_001",
            agent_id="research",
            entity_type="forensics_signal",
            symbol="BTCUSDT",
            direction="BUY",
            confidence=0.85,
            attributes={"spoofing": "false"},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        assert sig.signal_id == "sig_001"
        assert sig.confidence == 0.85
        node_dict = sig.to_node_dict()
        assert node_dict["node_id"] == "sig_001"
        assert node_dict["attributes"]["direction"] == "BUY"

    def test_signal_node_roundtrip(self) -> None:
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        sig = SignalNode(
            signal_id="sig_002",
            agent_id="analyst",
            entity_type="decision",
            symbol="ETHUSDT",
            direction="SELL",
            confidence=0.72,
            attributes={"reason": "vwap_deviation"},
            source_uri="agent://analyst/v1",
            priority=SignalPriority.ANALYST,
            parent_signal_ids=["sig_001"],
        )
        node_dict = sig.to_node_dict()
        restored = SignalNode.from_node_dict(node_dict)
        assert restored is not None
        assert restored.signal_id == "sig_002"
        assert restored.direction == "SELL"
        assert restored.confidence == 0.72
        assert restored.parent_signal_ids == ["sig_001"]

    def test_signal_node_invalid_returns_none(self) -> None:
        from intelligence.memory_agent.protocol import SignalNode
        result = SignalNode.from_node_dict({"invalid": "data"})
        assert result is None

    def test_agent_message_creation(self) -> None:
        from intelligence.memory_agent.protocol import AgentMessage
        msg = AgentMessage(
            message_id="msg_001",
            from_agent="research",
            to_agent="analyst",
            message_type="ALERT",
            payload={"spoofing_detected": True},
            source_uri="agent://research/v1",
        )
        node_dict = msg.to_node_dict()
        assert node_dict["entity_type"] == "agent_message"
        assert node_dict["attributes"]["to_agent"] == "analyst"


class TestMemoryGraphAgent:
    def test_publish_and_retrieve_signal(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        orchestrator = MemoryGraphAgent(store, "research")
        sig = SignalNode(
            signal_id="pub_test_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="BTCUSDT",
            direction="BUY",
            confidence=0.8,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        assert orchestrator.publish_signal(sig) is True
        chain = orchestrator.get_signal_chain("BTCUSDT")
        assert len(chain) >= 1
        assert chain[0].signal_id == "pub_test_1"

    def test_deduplication_blocks_duplicate(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        orchestrator = MemoryGraphAgent(store, "research")
        sig1 = SignalNode(
            signal_id="dedup_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="ETHUSDT",
            direction="BUY",
            confidence=0.7,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        sig2 = SignalNode(
            signal_id="dedup_2",
            agent_id="research",
            entity_type="test_signal",
            symbol="ETHUSDT",
            direction="BUY",
            confidence=0.75,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        assert orchestrator.publish_signal(sig1) is True
        assert orchestrator.publish_signal(sig2) is False  # duplicate

    def test_different_direction_not_duplicate(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        orchestrator = MemoryGraphAgent(store, "research")
        sig1 = SignalNode(
            signal_id="dir_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="SOLUSDT",
            direction="BUY",
            confidence=0.7,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        sig2 = SignalNode(
            signal_id="dir_2",
            agent_id="research",
            entity_type="test_signal",
            symbol="SOLUSDT",
            direction="SELL",
            confidence=0.6,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        assert orchestrator.publish_signal(sig1) is True
        assert orchestrator.publish_signal(sig2) is True  # different direction

    def test_get_upstream_signals(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        research_orch = MemoryGraphAgent(store, "research")
        analyst_orch = MemoryGraphAgent(store, "analyst")

        sig = SignalNode(
            signal_id="upstream_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="AVAXUSDT",
            direction="BUY",
            confidence=0.9,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        research_orch.publish_signal(sig)

        upstream = analyst_orch.get_upstream_signals(
            "AVAXUSDT", SignalPriority.ANALYST
        )
        assert len(upstream) >= 1
        assert upstream[0].agent_id == "research"

    def test_send_and_receive_message(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        store = _make_store()
        sender = MemoryGraphAgent(store, "research")
        receiver = MemoryGraphAgent(store, "analyst")

        assert sender.send_message(
            to_agent="analyst",
            message_type="ALERT",
            payload={"warning": "high_volatility"},
        ) is True

        messages = receiver.get_messages(message_type="ALERT")
        assert len(messages) >= 1
        attrs = messages[0].get("attributes", {})
        assert attrs.get("from_agent") == "research"

    def test_register_and_process_handler(self) -> None:
        from intelligence.memory_agent.orchestrator import MemoryGraphAgent
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority, SignalStatus,
        )
        store = _make_store()
        orch = MemoryGraphAgent(store, "analyst")

        def handle_research(sig: SignalNode) -> Optional[SignalNode]:
            return SignalNode(
                signal_id=f"decision_{sig.signal_id}",
                agent_id="analyst",
                entity_type="decision",
                symbol=sig.symbol,
                direction=sig.direction,
                confidence=sig.confidence * 0.9,
                attributes={"based_on": sig.signal_id},
                source_uri="agent://analyst/v1",
                priority=SignalPriority.ANALYST,
                parent_signal_ids=[sig.signal_id],
            )

        orch.register_handler("raw_signal", handle_research)

        input_sig = SignalNode(
            signal_id="raw_1",
            agent_id="analyst",
            entity_type="raw_signal",
            symbol="DOTUSDT",
            direction="BUY",
            confidence=0.8,
            attributes={},
            source_uri="agent://analyst/v1",
            priority=SignalPriority.RESEARCH,
        )
        orch.publish_signal(input_sig)

        processed = orch.process_pending_signals("raw_signal")
        assert len(processed) >= 1
        assert processed[0].entity_type == "decision"
        assert processed[0].parent_signal_ids == ["raw_1"]


class TestNeuralRouter:
    def test_connect_and_get_weight(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("research", "analyst", weight=1.5)
        assert router.get_weight("research", "analyst") == 1.5

    def test_default_weight_is_one(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        assert router.get_weight("unknown", "unknown") == 1.0

    def test_disconnect_removes_synapse(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("a", "b", weight=1.8)
        router.disconnect("a", "b")
        assert router.get_weight("a", "b") == 1.0

    def test_weight_clamped_to_bounds(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("a", "b", weight=99.0)
        assert router.get_weight("a", "b") == 2.0
        router.connect("c", "d", weight=-5.0)
        assert router.get_weight("c", "d") == 0.1

    def test_subscribe_and_route(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        router = NeuralRouter(store)
        received: list[SignalNode] = []

        def on_signal(sig: SignalNode) -> None:
            received.append(sig)

        router.subscribe("test_signal", on_signal)

        sig = SignalNode(
            signal_id="route_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="BTCUSDT",
            direction="BUY",
            confidence=0.8,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        result = router.route_signal(sig)
        assert result is True
        assert len(received) == 1
        assert received[0].signal_id == "route_1"

    def test_unsubscribe_stops_routing(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        router = NeuralRouter(store)
        received: list[SignalNode] = []

        def on_signal(sig: SignalNode) -> None:
            received.append(sig)

        router.subscribe("test_signal", on_signal)
        router.unsubscribe("test_signal", on_signal)

        sig = SignalNode(
            signal_id="unsub_1",
            agent_id="research",
            entity_type="test_signal",
            symbol="BTCUSDT",
            direction="BUY",
            confidence=0.8,
            attributes={},
            source_uri="agent://research/v1",
            priority=SignalPriority.RESEARCH,
        )
        router.route_signal(sig)
        assert len(received) == 0

    def test_inhibition_blocks_routing(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        router = NeuralRouter(store)
        router.add_inhibitor("risk_manager", "execution")
        router.emit_inhibit("risk_manager", "execution", "drawdown too high")

        assert router.is_inhibited("execution") is True

        received: list[SignalNode] = []
        router.subscribe("exec_signal", lambda s: received.append(s))

        sig = SignalNode(
            signal_id="blocked_1",
            agent_id="execution",
            entity_type="exec_signal",
            symbol="BTCUSDT",
            direction="BUY",
            confidence=0.9,
            attributes={},
            source_uri="agent://execution/v1",
            priority=SignalPriority.EXECUTION,
        )
        result = router.route_signal(sig)
        assert result is False
        assert len(received) == 0

    def test_no_inhibition_allows_routing(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        from intelligence.memory_agent.protocol import (
            SignalNode, SignalPriority,
        )
        store = _make_store()
        router = NeuralRouter(store)
        assert router.is_inhibited("analyst") is False

        sig = SignalNode(
            signal_id="free_1",
            agent_id="analyst",
            entity_type="decision",
            symbol="ETHUSDT",
            direction="SELL",
            confidence=0.7,
            attributes={},
            source_uri="agent://analyst/v1",
            priority=SignalPriority.ANALYST,
        )
        assert router.route_signal(sig) is True

    def test_plasticity_increases_on_correct(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("research", "analyst", weight=1.0)
        new_w = router.apply_plasticity("research", "analyst", was_correct=True)
        assert new_w > 1.0

    def test_plasticity_decreases_on_wrong(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("research", "analyst", weight=1.0)
        new_w = router.apply_plasticity("research", "analyst", was_correct=False)
        assert new_w < 1.0

    def test_plasticity_respects_bounds(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("a", "b", weight=0.1)
        for _ in range(50):
            router.apply_plasticity("a", "b", was_correct=False)
        assert router.get_weight("a", "b") >= 0.1

    def test_get_topology(self) -> None:
        from intelligence.memory_agent.neural import NeuralRouter
        store = _make_store()
        router = NeuralRouter(store)
        router.connect("a", "b", weight=1.5)
        router.add_inhibitor("risk", "exec")
        topo = router.get_topology()
        assert "a->b" in topo["synapses"]
        assert "exec" in topo["inhibitors"]
        assert topo["running"] is False
