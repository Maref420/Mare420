from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryRecord, MemoryType


class MemoryForgettingEngine:
    """Governed lifecycle boundary for memory removal.

    Governance rules enforced:
    - direct_storage_deletion_forbidden
    - agent_direct_deletion_forbidden
    - controlled_forgetting_required
    - working memory automatic forgetting is allowed
    - episodic memory forgetting is policy-controlled
    - semantic memory requires explicit policy
    - procedural memory is never automatically forgotten
    - every attempt is audited with the real result
    """

    POLICY_ID = "memory-lifecycle-policy:v1"

    def __init__(
        self,
        kernel: MemoryKernel,
        audit_sink: AuditSink,
    ) -> None:
        self._kernel = kernel
        self._audit_sink = audit_sink

    def forget(
        self,
        memory_id: str,
        *,
        operation_id: str,
        agent_id: str,
        explicit_policy_id: str | None = None,
        automatic: bool = False,
    ) -> bool:
        """Forget a memory record only if lifecycle policy permits it.

        Returns:
            True if a record was actually deleted.
            False if deletion was denied, record missing, or storage failed.
        """
        self._validate_required(memory_id, operation_id, agent_id)

        record = self._kernel.retrieve(memory_id)
        if record is None:
            self._audit_forget(
                memory_id=memory_id,
                operation_id=operation_id,
                agent_id=agent_id,
                result=AuditResult.FAILURE,
                metadata={
                    "reason": "memory_not_found",
                    "automatic": automatic,
                    "explicit_policy_id": explicit_policy_id,
                },
            )
            return False

        allowed, reason = self._is_forgetting_allowed(
            record,
            explicit_policy_id=explicit_policy_id,
            automatic=automatic,
        )
        if not allowed:
            self._audit_forget(
                memory_id=memory_id,
                operation_id=operation_id,
                agent_id=agent_id,
                result=AuditResult.FAILURE,
                metadata={
                    "reason": reason,
                    "memory_type": record.memory_type.value,
                    "automatic": automatic,
                    "explicit_policy_id": explicit_policy_id,
                },
            )
            return False

        try:
            deleted = self._kernel.delete(memory_id)
        except Exception as exc:
            self._audit_forget(
                memory_id=memory_id,
                operation_id=operation_id,
                agent_id=agent_id,
                result=AuditResult.FAILURE,
                metadata={
                    "reason": "storage_delete_exception",
                    "error": str(exc),
                    "memory_type": record.memory_type.value,
                    "automatic": automatic,
                    "explicit_policy_id": explicit_policy_id,
                },
            )
            return False

        self._audit_forget(
            memory_id=memory_id,
            operation_id=operation_id,
            agent_id=agent_id,
            result=AuditResult.SUCCESS if deleted else AuditResult.FAILURE,
            metadata={
                "reason": "deleted" if deleted else "storage_delete_returned_false",
                "memory_type": record.memory_type.value,
                "automatic": automatic,
                "explicit_policy_id": explicit_policy_id,
            },
        )
        return deleted

    def forget_if_expired_working_memory(
        self,
        memory_id: str,
        *,
        operation_id: str,
        agent_id: str,
    ) -> bool:
        """Automatically forget expired working memory.

        Expiry source:
            record.metadata["expires_at"]

        Accepted timestamp:
            ISO-8601 string, including trailing Z.
        """
        self._validate_required(memory_id, operation_id, agent_id)

        record = self._kernel.retrieve(memory_id)
        if record is None:
            return False

        if record.memory_type is not MemoryType.WORKING:
            return False

        expires_at_raw = record.metadata.get("expires_at")
        if not isinstance(expires_at_raw, str) or not expires_at_raw.strip():
            return False

        try:
            expires_at = datetime.fromisoformat(
                expires_at_raw.replace("Z", "+00:00")
            )
        except ValueError:
            self._audit_forget(
                memory_id=memory_id,
                operation_id=operation_id,
                agent_id=agent_id,
                result=AuditResult.FAILURE,
                metadata={
                    "reason": "invalid_expires_at",
                    "expires_at": expires_at_raw,
                    "memory_type": record.memory_type.value,
                    "automatic": True,
                    "explicit_policy_id": self.POLICY_ID,
                },
            )
            return False

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at > datetime.now(timezone.utc):
            return False

        return self.forget(
            memory_id,
            operation_id=operation_id,
            agent_id=agent_id,
            explicit_policy_id=self.POLICY_ID,
            automatic=True,
        )

    def _is_forgetting_allowed(
        self,
        record: MemoryRecord,
        *,
        explicit_policy_id: str | None,
        automatic: bool,
    ) -> tuple[bool, str]:
        if record.memory_type is MemoryType.WORKING:
            return True, "working_memory_forgetting_allowed"

        if record.memory_type is MemoryType.EPISODIC:
            if automatic and not explicit_policy_id:
                return False, "episodic_automatic_forgetting_requires_policy"
            return True, "episodic_policy_controlled_forgetting_allowed"

        if record.memory_type is MemoryType.SEMANTIC:
            if not explicit_policy_id:
                return False, "semantic_forgetting_requires_explicit_policy"
            return True, "semantic_explicit_policy_forgetting_allowed"

        if record.memory_type is MemoryType.PROCEDURAL:
            if automatic:
                return False, "procedural_automatic_forgetting_forbidden"
            if not explicit_policy_id:
                return False, "procedural_forgetting_requires_explicit_policy"
            return True, "procedural_explicit_policy_forgetting_allowed"

        return False, "unknown_memory_type"

    def _audit_forget(
        self,
        *,
        memory_id: str,
        operation_id: str,
        agent_id: str,
        result: AuditResult,
        metadata: dict,
    ) -> None:
        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=str(uuid4()),
                event_type=AuditEventType.MEMORY_FORGET,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=datetime.now(timezone.utc),
                action=AuditAction.REQUESTED,
                resource=memory_id,
                result=result,
                metadata=metadata,
            )
        )

    @staticmethod
    def _validate_required(
        memory_id: str,
        operation_id: str,
        agent_id: str,
    ) -> None:
        if not memory_id:
            raise ValueError("memory_id must not be empty.")
        if not operation_id:
            raise ValueError("operation_id must not be empty.")
        if not agent_id:
            raise ValueError("agent_id must not be empty.")
