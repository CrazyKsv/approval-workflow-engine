from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ROLES = {"admin", "manager", "finance", "vp", "employee"}
CONDITION_OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains"}

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


# --- Auth / directory -------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    is_active: bool


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    members: list[UserOut] = []


# --- Workflow templates ------------------------------------------------------

class TemplateFieldSpec(BaseModel):
    name: str
    label: str
    type: Literal["string", "number", "date", "boolean"] = "string"
    required: bool = False


class ConditionSpec(BaseModel):
    field: str
    op: str
    value: Any

    @field_validator("op")
    @classmethod
    def _valid_op(cls, v: str) -> str:
        if v not in CONDITION_OPS:
            raise ValueError(f"op must be one of {sorted(CONDITION_OPS)}")
        return v


class TemplateStepIn(BaseModel):
    step_order: int = Field(ge=1)
    name: str
    approver_type: Literal["user", "group", "role"]
    approver_user_id: int | None = None
    approver_group_id: int | None = None
    approver_role: str | None = None
    approval_mode: Literal["any", "all"] = "any"
    condition: ConditionSpec | None = None
    sla_hours: int | None = Field(default=None, ge=1)
    escalation_user_id: int | None = None
    escalation_role: str | None = None


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    fields: list[TemplateFieldSpec] = []
    steps: list[TemplateStepIn] = Field(min_length=1)


class TemplateUpdate(BaseModel):
    is_active: bool


class TemplateStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    name: str
    approver_type: str
    approver_user_id: int | None
    approver_group_id: int | None
    approver_role: str | None
    approval_mode: str
    condition: dict | None
    sla_hours: int | None
    escalation_user_id: int | None
    escalation_role: str | None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    category: str | None
    fields: list[TemplateFieldSpec]
    is_active: bool
    version: int
    created_by_id: int | None
    created_at: datetime
    steps: list[TemplateStepOut]


# --- Requests / decisions ----------------------------------------------------

class RequestCreate(BaseModel):
    template_id: int
    title: str
    description: str | None = None
    amount: float | None = None
    data: dict[str, Any] = {}


class RequestResubmit(BaseModel):
    title: str | None = None
    description: str | None = None
    amount: float | None = None
    data: dict[str, Any] | None = None


class StepApproverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    approver_id: int
    status: str
    is_escalation: bool
    approver: UserOut


class StepInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    name: str
    approval_mode: str
    status: str
    activated_at: datetime | None
    completed_at: datetime | None
    due_at: datetime | None
    escalated: bool
    approvers: list[StepApproverOut]


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_instance_id: int
    decision: str
    comment: str | None
    created_at: datetime
    approver: UserOut
    acting_user: UserOut


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    title: str
    description: str | None
    amount: float | None
    data: dict
    status: str
    current_step_order: int | None
    created_at: datetime
    completed_at: datetime | None
    requester: UserOut
    template: TemplateOut | None = None


class RequestDetailOut(RequestOut):
    steps: list[StepInstanceOut]
    decisions: list[DecisionOut]


class DecisionCreate(BaseModel):
    decision: Literal["approved", "rejected", "changes_requested"]
    comment: str | None = None


class InboxItemOut(BaseModel):
    request: RequestOut
    step: StepInstanceOut
    on_behalf_of: UserOut | None = None  # set when acting via delegation


class StatusFeedItemOut(BaseModel):
    request: RequestOut
    message: str  # e.g. "approved by Mark Manager; waiting for finance approval"


# --- Delegations ---------------------------------------------------------------

class DelegationCreate(BaseModel):
    delegate_id: int
    starts_at: datetime
    ends_at: datetime
    reason: str | None = None


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    delegator: UserOut
    delegate: UserOut
    starts_at: datetime
    ends_at: datetime
    reason: str | None
    is_active: bool
    created_at: datetime


# --- Audit ----------------------------------------------------------------------

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    details: dict
    created_at: datetime
    actor: UserOut | None


# --- Agent ------------------------------------------------------------------------

class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: int | None = None


class AgentToolEvent(BaseModel):
    tool_name: str
    arguments: dict
    result: dict | None
    latency_ms: int | None
    error: str | None = None


class AgentChatResponse(BaseModel):
    conversation_id: int
    reply: str
    tool_events: list[AgentToolEvent] = []


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str | None
    tool_name: str | None
    tool_args: dict | None
    tool_result: dict | None
    latency_ms: int | None
    error: str | None
    created_at: datetime


class AgentConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime


class AgentConversationDetailOut(AgentConversationOut):
    messages: list[AgentMessageOut]
