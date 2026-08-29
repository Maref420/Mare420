from datetime import UTC, datetime
from uuid import uuid4

from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.agent_control_plane.identity.models import AgentStatus
from intelligence.agent_control_plane.permissions.engine import PermissionEngine
from intelligence.agent_control_plane.permissions.models import Capability
from intelligence.agent_control_plane.policy.engine import AgentPolicyEngine
from intelligence.agent_control_plane.registry.registry import AgentRegistry
from intelligence.memory_system.forgetting.engine import MemoryForgettingEngine
from intelligence.memory_system.memory_kernel.kernel import MemoryKernel
from intelligence.memory_system.models.memory_record import MemoryRecord
from intelligence.memory_system.retrieval_engine.engine import MemoryRetrievalEngine


class AgentGateway:
    """Single controlled entry point for Agent memory operations."""

    def __init__(
        self,
        registry: AgentRegistry,
        permissions: PermissionEngine,
        policy: AgentPolicyEngine,
        kernel: MemoryKernel,
        audit_sink: AuditSink,
        forgetting: MemoryForgettingEngine,
        retrieval: MemoryRetrievalEngine,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._policy = policy
        self._kernel = kernel
        self._audit_sink = audit_sink
        self._forgetting = forgetting
        self._retrieval = retrieval

    def _authorize(
        self,
        agent_id: str,
        capability: Capability,
        *,
        event_type: AuditEventType,
        operation_id: str,
        resource: str,
    ) -> None:
        try:
            identity = self._registry.get(agent_id)

            if identity is None:
                raise PermissionError("Unknown Agent.")

            if identity.status not in {
                AgentStatus.VALIDATED,
                AgentStatus.READY,
                AgentStatus.RUNNING,
            }:
                raise PermissionError(
                    "Agent is not authorized for execution."
                )

            self._policy.validate(capability)
            self._permissions.require(agent_id, capability)

        except Exception:
            self._audit(
                event_type=event_type,
                action=AuditAction.FAILED,
                result=AuditResult.FAILURE,
                operation_id=operation_id,
                agent_id=agent_id,
                resource=resource,
            )
            raise

    def _audit(
        self,
        *,
        event_type: AuditEventType,
        action: AuditAction,
        result: AuditResult,
        operation_id: str,
        agent_id: str,
        resource: str,
    ) -> None:
        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=str(uuid4()),
                event_type=event_type,
                operation_id=operation_id,
                agent_id=agent_id,
                timestamp=datetime.now(UTC),
                action=action,
                resource=resource,
                result=result,
                metadata={},
            )
        )

    def retrieve(
        self,
        agent_id: str,
        memory_id: str,
        *,
        operation_id: str,
    ) -> MemoryRecord | None:
        self._authorize(
            agent_id,
            Capability.MEMORY_RETRIEVE,
            event_type=AuditEventType.MEMORY_RETRIEVE,
            operation_id=operation_id,
            resource=memory_id,
        )

        self._audit(
            event_type=AuditEventType.MEMORY_RETRIEVE,
            action=AuditAction.REQUESTED,
            result=AuditResult.SUCCESS,
            operation_id=operation_id,
            agent_id=agent_id,
            resource=memory_id,
        )

        try:
            result = self._retrieval.retrieve(memory_id)
        except Exception:
            self._audit(
                event_type=AuditEventType.MEMORY_RETRIEVE,
                action=AuditAction.FAILED,
                result=AuditResult.FAILURE,
                operation_id=operation_id,
                agent_id=agent_id,
                resource=memory_id,
            )
            raise

        self._audit(
            event_type=AuditEventType.MEMORY_RETRIEVE,
            action=AuditAction.COMPLETED,
            result=AuditResult.SUCCESS,
            operation_id=operation_id,
            agent_id=agent_id,
            resource=memory_id,
        )

        return result

    def store(
        self,
        agent_id: str,
        record: MemoryRecord,
        *,
        operation_id: str,
    ) -> None:
        self._authorize(
            agent_id,
            Capability.MEMORY_STORE,
            event_type=AuditEventType.MEMORY_STORE,
            operation_id=operation_id,
            resource=record.memory_id,
        )

        self._audit(
            event_type=AuditEventType.MEMORY_STORE,
            action=AuditAction.REQUESTED,
            result=AuditResult.SUCCESS,
            operation_id=operation_id,
            agent_id=agent_id,
            resource=record.memory_id,
        )

        try:
            self._kernel.store(record)
        except Exception:
            self._audit(
                event_type=AuditEventType.MEMORY_STORE,
                action=AuditAction.FAILED,
                result=AuditResult.FAILURE,
                operation_id=operation_id,
                agent_id=agent_id,
                resource=record.memory_id,
            )
            raise

        self._audit(
            event_type=AuditEventType.MEMORY_STORE,
            action=AuditAction.COMPLETED,
            result=AuditResult.SUCCESS,
            operation_id=operation_id,
            agent_id=agent_id,
            resource=record.memory_id,
        )

    def forget(
        self,
        agent_id: str,
        memory_id: str,
        *,
        operation_id: str,
    ) -> bool:
        self._authorize(
            agent_id,
            Capability.MEMORY_FORGET,
            event_type=AuditEventType.MEMORY_FORGET,
            operation_id=operation_id,
            resource=memory_id,
        )

        return self._forgetting.forget(
            memory_id,
            operation_id=operation_id,
            agent_id=agent_id,
        )
