from intelligence.agent_control_plane.audit.interface import AuditSink
from intelligence.agent_control_plane.audit.models import (
    AuditAction,
    AuditEventType,
    AuditRecord,
    AuditResult,
)
from intelligence.agent_control_plane.communication.models import (
    AgentMessage,
    CommunicationPolicy,
    MessageStatus,
)
from intelligence.agent_control_plane.identity.models import AgentStatus
from intelligence.agent_control_plane.registry.registry import AgentRegistry


class AgentCommunicationEngine:
    """Controlled Agent-to-Agent and Agent-to-System communication."""

    def __init__(
        self,
        registry: AgentRegistry,
        policy: CommunicationPolicy,
        audit_sink: AuditSink,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._audit_sink = audit_sink
        self._messages: dict[str, AgentMessage] = {}

    def _audit(
        self,
        *,
        message: AgentMessage,
        action: AuditAction,
        result: AuditResult,
    ) -> None:
        self._audit_sink.record(
            AuditRecord(
                contract_version="1.0",
                event_id=message.message_id,
                event_type=AuditEventType.COMMUNICATION_SEND,
                operation_id=message.message_id,
                agent_id=message.sender_id,
                timestamp=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ),
                action=action,
                resource=message.recipient_id,
                result=result,
                metadata={
                    "message_type": message.message_type.value,
                    "message_status": message.status.value,
                },
            )
        )

    def send(self, message: AgentMessage) -> AgentMessage:
        if message.message_id in self._messages:
            raise ValueError("Message is already registered.")

        self._audit(
            message=message,
            action=AuditAction.REQUESTED,
            result=AuditResult.SUCCESS,
        )

        try:
            return self._send_authorized(message)
        except Exception:
            self._audit(
                message=message,
                action=AuditAction.FAILED,
                result=AuditResult.FAILURE,
            )
            raise

    def _send_authorized(
        self,
        message: AgentMessage,
    ) -> AgentMessage:
        sender = self._registry.get(message.sender_id)
        if sender is None:
            raise PermissionError("Unknown sender Agent.")

        if sender.status not in {
            AgentStatus.READY,
            AgentStatus.RUNNING,
        }:
            raise PermissionError("Sender Agent is not authorized.")

        recipient = self._registry.get(message.recipient_id)

        if recipient is None:
            if not self._policy.allow_agent_to_system:
                raise PermissionError(
                    "Agent-to-system communication is disabled."
                )
        else:
            if not self._policy.allow_agent_to_agent:
                raise PermissionError(
                    "Agent-to-Agent communication is disabled."
                )

            if recipient.status in {
                AgentStatus.CREATED,
                AgentStatus.VALIDATED,
                AgentStatus.SUSPENDED,
                AgentStatus.TERMINATED,
            }:
                raise PermissionError(
                    "Recipient Agent is not available."
                )

        delivered = message.model_copy(
            update={"status": MessageStatus.DELIVERED}
        )
        self._messages[message.message_id] = delivered

        self._audit(
            message=delivered,
            action=AuditAction.COMPLETED,
            result=AuditResult.SUCCESS,
        )

        return delivered

    def get(self, message_id: str) -> AgentMessage | None:
        if not message_id:
            raise ValueError("message_id must not be empty.")

        return self._messages.get(message_id)

    def reject(self, message_id: str) -> AgentMessage:
        message = self.get(message_id)

        if message is None:
            raise KeyError("Unknown message.")

        if message.status is not MessageStatus.CREATED:
            raise ValueError("Only created messages may be rejected.")

        rejected = message.model_copy(
            update={"status": MessageStatus.REJECTED}
        )
        self._messages[message_id] = rejected
        return rejected
