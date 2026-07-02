"""SQLAlchemy models for the approval workflow engine.

JSON columns use the portable JSON type with a JSONB variant on PostgreSQL so the
same models run on SQLite in tests.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Directory -------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="employee")  # admin|manager|finance|vp|employee
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    groups: Mapped[list["Group"]] = relationship(secondary="user_groups", back_populates="members")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[User]] = relationship(secondary="user_groups", back_populates="groups")


class UserGroup(Base):
    __tablename__ = "user_groups"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)


# --- Workflow definition ----------------------------------------------------

class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    # Declared input fields: [{"name","label","type","required"}]
    fields: Mapped[list] = mapped_column(JSONVariant, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    steps: Mapped[list["TemplateStep"]] = relationship(
        back_populates="template", order_by="TemplateStep.step_order", cascade="all, delete-orphan"
    )
    created_by: Mapped[User | None] = relationship()


class TemplateStep(Base):
    __tablename__ = "template_steps"
    __table_args__ = (UniqueConstraint("template_id", "step_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workflow_templates.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    approver_type: Mapped[str] = mapped_column(String(20))  # user|group|role
    approver_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approver_group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"))
    approver_role: Mapped[str | None] = mapped_column(String(50))
    approval_mode: Mapped[str] = mapped_column(String(10), default="any")  # any|all
    # Conditional routing, e.g. {"field": "amount", "op": ">", "value": 10000}
    condition: Mapped[dict | None] = mapped_column(JSONVariant)
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    escalation_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    escalation_role: Mapped[str | None] = mapped_column(String(50))

    template: Mapped[WorkflowTemplate] = relationship(back_populates="steps")
    approver_user: Mapped[User | None] = relationship(foreign_keys=[approver_user_id])
    approver_group: Mapped[Group | None] = relationship(foreign_keys=[approver_group_id])


# --- Workflow instances -----------------------------------------------------

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workflow_templates.id"), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    data: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    # pending|approved|rejected|changes_requested|cancelled
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    current_step_order: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[WorkflowTemplate] = relationship()
    requester: Mapped[User] = relationship()
    steps: Mapped[list["StepInstance"]] = relationship(
        back_populates="request", order_by="StepInstance.step_order", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="request", order_by="Decision.created_at", cascade="all, delete-orphan"
    )


class StepInstance(Base):
    __tablename__ = "step_instances"
    __table_args__ = (Index("ix_step_instances_status_due", "status", "due_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    template_step_id: Mapped[int | None] = mapped_column(ForeignKey("template_steps.id"))
    step_order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    approval_mode: Mapped[str] = mapped_column(String(10), default="any")
    # pending|active|approved|rejected|skipped
    status: Mapped[str] = mapped_column(String(20), default="pending")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)

    request: Mapped[ApprovalRequest] = relationship(back_populates="steps")
    template_step: Mapped[TemplateStep | None] = relationship()
    approvers: Mapped[list["StepApprover"]] = relationship(
        back_populates="step_instance", cascade="all, delete-orphan"
    )


class StepApprover(Base):
    """Concrete approver authorities resolved when a step activates.

    Group/role approvers are expanded to users here so 'who could approve and why'
    is a stable snapshot. Delegation is resolved at decision time (see engine).
    """

    __tablename__ = "step_approvers"
    __table_args__ = (Index("ix_step_approvers_approver_status", "approver_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    step_instance_id: Mapped[int] = mapped_column(ForeignKey("step_instances.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    is_escalation: Mapped[bool] = mapped_column(Boolean, default=False)

    step_instance: Mapped[StepInstance] = relationship(back_populates="approvers")
    approver: Mapped[User] = relationship()


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    step_instance_id: Mapped[int] = mapped_column(ForeignKey("step_instances.id", ondelete="CASCADE"))
    # approver_id: whose authority was exercised; acting_user_id: who actually acted
    # (they differ when a delegate decides on behalf of a delegator).
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    acting_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))  # approved|rejected|changes_requested
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[ApprovalRequest] = relationship(back_populates="decisions")
    approver: Mapped[User] = relationship(foreign_keys=[approver_id])
    acting_user: Mapped[User] = relationship(foreign_keys=[acting_user_id])


class Delegation(Base):
    __tablename__ = "delegations"
    __table_args__ = (
        Index("ix_delegations_delegator", "delegator_id", "is_active"),
        Index("ix_delegations_delegate", "delegate_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    delegator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    delegate_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    delegator: Mapped[User] = relationship(foreign_keys=[delegator_id])
    delegate: Mapped[User] = relationship(foreign_keys=[delegate_id])


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_request_created", "request_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("approval_requests.id", ondelete="SET NULL"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSONVariant, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    actor: Mapped[User | None] = relationship()


# --- Agent conversations ----------------------------------------------------

class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship()
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="conversation", order_by="AgentMessage.id", cascade="all, delete-orphan"
    )


class AgentMessage(Base):
    """One event in a conversation: user/assistant/tool message.

    Tool invocations are persisted with args, result, latency and error so the whole
    orchestration is observable and replayable.
    """

    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("agent_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|tool
    content: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list | None] = mapped_column(JSONVariant)  # assistant tool_calls (OpenAI shape)
    tool_call_id: Mapped[str | None] = mapped_column(String(100))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_args: Mapped[dict | None] = mapped_column(JSONVariant)
    tool_result: Mapped[dict | None] = mapped_column(JSONVariant)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[AgentConversation] = relationship(back_populates="messages")
