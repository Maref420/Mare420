"""Tests for Memory Kernel — governance-compliant pytest suite.

Data Flow:
1. Test Runner invokes pytest with test_memory_kernel.py.
2. Pytest loads fixtures: mock_storage, mock_validator, valid_record.
3. memory_kernel fixture patches MemoryValidator, instantiates MemoryKernel.
4. Test functions invoke MemoryKernel methods (store, retrieve, delete, validate_type).
5. MemoryKernel delegates validation to mocked MemoryValidator.
6. MemoryKernel delegates storage operations to mock_storage.
7. Assertions verify mock calls, return values, and raised exceptions.

Governance compliance:
- python-policy: type_hints_required, no_bare_except, explicit_dependency_injection
- global-policy: test_validation required, no_placeholder_artifacts
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import (
    MemoryRecord,
    MemoryType,
    ValidationStatus,
)
from intelligence.memory_system.storage.interface import MemoryStorage


@pytest.fixture
def valid_record() -> MemoryRecord:
    """A fully valid, validated memory record for testing."""
    return MemoryRecord(
        memory_id="test-mem-001",
        operation_id="op-001",
        agent_id="agent-test",
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(tz=timezone.utc),
        content={"event": "test event", "value": 42},
        metadata={"source": "test"},
        validation_status=ValidationStatus.VALIDATED,
    )


@pytest.fixture
def unvalidated_record() -> MemoryRecord:
    """A record that has not passed validation."""
    return MemoryRecord(
        memory_id="test-mem-bad",
        operation_id="op-bad",
        agent_id="agent-test",
        memory_type=MemoryType.EPISODIC,
        created_at=datetime.now(tz=timezone.utc),
        content={"event": "bad"},
        metadata={},
        validation_status=ValidationStatus.REJECTED,
    )


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock storage implementing MemoryStorage interface."""
    storage = MagicMock(spec=MemoryStorage)
    storage.store.return_value = None
    storage.retrieve.return_value = None
    storage.delete.return_value = False
    return storage


@pytest.fixture
def mock_validator() -> MagicMock:
    """Mock validator that returns the record as-is by default."""
    validator = MagicMock()
    return validator


@pytest.fixture
def memory_kernel(mock_storage: MagicMock, mock_validator: MagicMock) -> MemoryKernel:
    """MemoryKernel with mocked dependencies injected."""
    with patch(
        "intelligence.memory_system.memory_kernel.kernel.MemoryValidator",
        return_value=mock_validator,
    ):
        kernel = MemoryKernel(storage=mock_storage)
    return kernel


class TestMemoryKernelInitialization:
    def test_initialization_configures_storage_and_validator(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
    ) -> None:
        assert memory_kernel._storage is mock_storage
        assert memory_kernel._validator is not None


class TestMemoryKernelStore:
    def test_store_validated_record_calls_storage(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
        mock_validator: MagicMock,
        valid_record: MemoryRecord,
    ) -> None:
        mock_validator.validate.return_value = valid_record
        memory_kernel.store(valid_record)
        mock_validator.validate.assert_called_once_with(valid_record)
        mock_storage.store.assert_called_once_with(valid_record)

    def test_store_rejected_record_raises_value_error(
        self,
        memory_kernel: MemoryKernel,
        mock_validator: MagicMock,
        unvalidated_record: MemoryRecord,
    ) -> None:
        mock_validator.validate.return_value = unvalidated_record
        with pytest.raises(ValueError, match="Only validated memory may be stored"):
            memory_kernel.store(unvalidated_record)

    def test_store_does_not_call_storage_when_validation_fails(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
        mock_validator: MagicMock,
        unvalidated_record: MemoryRecord,
    ) -> None:
        mock_validator.validate.return_value = unvalidated_record
        with pytest.raises(ValueError):
            memory_kernel.store(unvalidated_record)
        mock_storage.store.assert_not_called()


class TestMemoryKernelRetrieve:
    def test_retrieve_returns_record_when_exists(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
        valid_record: MemoryRecord,
    ) -> None:
        mock_storage.retrieve.return_value = valid_record
        result = memory_kernel.retrieve("test-mem-001")
        assert result is valid_record
        mock_storage.retrieve.assert_called_once_with("test-mem-001")

    def test_retrieve_returns_none_for_missing_id(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.retrieve.return_value = None
        result = memory_kernel.retrieve("non-existent")
        assert result is None

    def test_retrieve_raises_value_error_on_empty_id(
        self,
        memory_kernel: MemoryKernel,
    ) -> None:
        with pytest.raises(ValueError, match="memory_id must not be empty"):
            memory_kernel.retrieve("")


class TestMemoryKernelDelete:
    def test_delete_returns_true_when_storage_confirms(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.delete.return_value = True
        result = memory_kernel.delete("mem-001")
        assert result is True
        mock_storage.delete.assert_called_once_with("mem-001")

    def test_delete_returns_false_when_storage_denies(
        self,
        memory_kernel: MemoryKernel,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.delete.return_value = False
        result = memory_kernel.delete("mem-002")
        assert result is False

    def test_delete_raises_value_error_on_empty_id(
        self,
        memory_kernel: MemoryKernel,
    ) -> None:
        with pytest.raises(ValueError, match="memory_id must not be empty"):
            memory_kernel.delete("")


class TestMemoryKernelValidateType:
    def test_validate_type_returns_true_for_matching_type(
        self,
        valid_record: MemoryRecord,
    ) -> None:
        result = MemoryKernel.validate_type(valid_record, MemoryType.EPISODIC)
        assert result is True

    def test_validate_type_returns_false_for_mismatched_type(
        self,
        valid_record: MemoryRecord,
    ) -> None:
        result = MemoryKernel.validate_type(valid_record, MemoryType.SEMANTIC)
        assert result is False

    def test_validate_type_works_for_all_memory_types(self) -> None:
        for mtype in MemoryType:
            record = MemoryRecord(
                memory_id=f"test-{mtype.value}",
                operation_id=f"op-{mtype.value}",
                agent_id="agent-test",
                memory_type=mtype,
                created_at=datetime.now(tz=timezone.utc),
                content="test",
                metadata={},
                validation_status=ValidationStatus.VALIDATED,
            )
            assert MemoryKernel.validate_type(record, mtype) is True
