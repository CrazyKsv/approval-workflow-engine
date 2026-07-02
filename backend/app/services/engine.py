"""Core workflow engine: routing, conditions, decisions, delegation, escalation.

All state changes flow through here (used by both REST routers and agent tools) so
authorization checks and audit writes are applied uniformly.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models import (
    ApprovalRequest,
    Decision,
    Delegation,
    Group,
    StepApprover,
    StepInstance,
    TemplateStep,
    User,
    WorkflowTemplate,
    utcnow,
)
from app.schemas import RequestCreate, RequestResubmit
from app.services.audit import write_audit


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# --- Conditions ---------------------------------------------------------------

def evaluate_condition(condition: dict | None, data: dict) -> bool:
    """Evaluate a routing condition like {"field": "amount", "op": ">", "value": 10000}.

    A step with no condition always applies. A missing field or a type mismatch
    evaluates to False (the step is skipped) rather than raising.
    """
    if not condition:
        return True
    field, op, expected = condition.get("field"), condition.get("op"), condition.get("value")
    if field not in data:
        return False
    actual = data[field]
    try:
        if op == "==":
            return _loose_eq(actual, expected)
        if op == "!=":
            return not _loose_eq(actual, expected)
        if op in (">", ">=", "<", "<="):
            a, e = float(actual), float(expected)
            return {">": a > e, ">=": a >= e, "<": a < e, "<=": a <= e}[op]
        if op == "in":
            return actual in expected
        if op == "not_in":
            return actual not in expected
        if op == "contains":
            return expected in actual
    except (TypeError, ValueError):
        return False
    return False


def _loose_eq(a, b) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def _eval_data(request: ApprovalRequest) -> dict:
    data = dict(request.data or {})
    if request.amount is not None:
        data.setdefault("amount", float(request.amount))
    return data


# --- Delegation ------------------------------------------------------------------

def active_delegator_ids(db: Session, user: User, at: datetime | None = None) -> set[int]:
    """Users who have currently delegated their approval authority to `user`."""
    at = at or utcnow()
    rows = db.scalars(
        select(Delegation).where(Delegation.delegate_id == user.id, Delegation.is_active.is_(True))
    ).all()
    return {d.delegator_id for d in rows if _aware(d.starts_at) <= at <= _aware(d.ends_at)}


# --- Approver resolution / step activation ------------------------------------------

def resolve_step_approvers(db: Session, tstep: TemplateStep) -> list[User]:
    if tstep.approver_type == "user":
        user = db.get(User, tstep.approver_user_id) if tstep.approver_user_id else None
        return [user] if user and user.is_active else []
    if tstep.approver_type == "group":
        group = db.get(Group, tstep.approver_group_id) if tstep.approver_group_id else None
        return [u for u in (group.members if group else []) if u.is_active]
    if tstep.approver_type == "role":
        return list(
            db.scalars(select(User).where(User.role == tstep.approver_role, User.is_active.is_(True)))
        )
    return []


def _activate_step(db: Session, request: ApprovalRequest, step: StepInstance) -> None:
    tstep = step.template_step
    approvers = resolve_step_approvers(db, tstep) if tstep else []
    # The requester should not approve their own request; drop them unless they are
    # the only possible approver.
    non_self = [u for u in approvers if u.id != request.requester_id]
    if non_self:
        approvers = non_self
    if not approvers:
        raise ConflictError(f"Step '{step.name}' has no resolvable approvers")

    step.status = "active"
    step.activated_at = utcnow()
    if tstep and tstep.sla_hours:
        step.due_at = step.activated_at + timedelta(hours=tstep.sla_hours)
    request.current_step_order = step.step_order

    seen: set[int] = set()
    for user in approvers:
        if user.id in seen:
            continue
        seen.add(user.id)
        db.add(StepApprover(step_instance=step, request_id=request.id, approver_id=user.id))

    write_audit(
        db, None, "step_activated", "step_instance", step.id, request.id,
        {"step": step.name, "approver_ids": sorted(seen), "due_at": step.due_at.isoformat() if step.due_at else None},
    )


def _advance_or_complete(db: Session, request: ApprovalRequest) -> None:
    next_step = next((s for s in sorted(request.steps, key=lambda s: s.step_order) if s.status == "pending"), None)
    if next_step is not None:
        _activate_step(db, request, next_step)
        return
    request.status = "approved"
    request.completed_at = utcnow()
    request.current_step_order = None
    write_audit(db, None, "request_approved", "approval_request", request.id, request.id, {})


# --- Submission ------------------------------------------------------------------

def validate_request_data(template: WorkflowTemplate, amount: float | None, data: dict) -> None:
    missing = []
    for field in template.fields or []:
        if not field.get("required"):
            continue
        name = field["name"]
        if name == "amount":
            if amount is None and data.get("amount") in (None, ""):
                missing.append(name)
        elif data.get(name) in (None, ""):
            missing.append(name)
    if missing:
        raise ValidationFailedError(f"Missing required fields: {', '.join(missing)}")


def submit_request(db: Session, requester: User, payload: RequestCreate) -> ApprovalRequest:
    template = db.get(WorkflowTemplate, payload.template_id)
    if template is None:
        raise NotFoundError("Workflow template not found")
    if not template.is_active:
        raise ConflictError("Workflow template is inactive")
    validate_request_data(template, payload.amount, payload.data)

    request = ApprovalRequest(
        template_id=template.id,
        requester_id=requester.id,
        title=payload.title,
        description=payload.description,
        amount=payload.amount,
        data=payload.data,
    )
    db.add(request)
    db.flush()
    write_audit(
        db, requester, "request_submitted", "approval_request", request.id, request.id,
        {"title": request.title, "template": template.name, "amount": payload.amount},
    )
    _route(db, request, template)
    db.flush()
    return request


def _route(db: Session, request: ApprovalRequest, template: WorkflowTemplate) -> None:
    """Create step instances (evaluating conditions against the request data) and
    activate the first applicable step."""
    data = _eval_data(request)
    for tstep in template.steps:
        applies = evaluate_condition(tstep.condition, data)
        step = StepInstance(
            request=request,
            template_step_id=tstep.id,
            step_order=tstep.step_order,
            name=tstep.name,
            approval_mode=tstep.approval_mode,
            status="pending" if applies else "skipped",
        )
        db.add(step)
        if not applies:
            write_audit(
                db, None, "step_skipped", "step_instance", None, request.id,
                {"step": tstep.name, "condition": tstep.condition},
            )
    db.flush()
    _advance_or_complete(db, request)


# --- Decisions -----------------------------------------------------------------------

def decide(db: Session, request_id: int, actor: User, decision: str, comment: str | None = None) -> ApprovalRequest:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise NotFoundError("Request not found")
    if request.status != "pending":
        raise ConflictError(f"Request is not awaiting decisions (status: {request.status})")

    step = next((s for s in request.steps if s.status == "active"), None)
    if step is None:
        raise ConflictError("Request has no active step")

    allowed_ids = {actor.id} | active_delegator_ids(db, actor)
    pending_auths = [a for a in step.approvers if a.status == "pending" and a.approver_id in allowed_ids]
    if not pending_auths:
        raise PermissionDeniedError("You are not a pending approver (or delegate) for this step")
    # Prefer acting on one's own authority over a delegated one.
    auth = next((a for a in pending_auths if a.approver_id == actor.id), pending_auths[0])
    on_behalf = auth.approver_id != actor.id

    db.add(
        Decision(
            request_id=request.id,
            step_instance_id=step.id,
            approver_id=auth.approver_id,
            acting_user_id=actor.id,
            decision=decision,
            comment=comment,
        )
    )
    write_audit(
        db, actor, f"decision_{decision}", "step_instance", step.id, request.id,
        {"step": step.name, "comment": comment, "on_behalf_of": auth.approver_id if on_behalf else None},
    )

    if decision == "approved":
        auth.status = "approved"
        pending_left = [a for a in step.approvers if a.status == "pending"]
        # 'any' mode: one approval completes the step. 'all' mode: everyone must
        # approve — except an escalation approver, whose approval overrides quorum.
        if step.approval_mode == "any" or not pending_left or auth.is_escalation:
            step.status = "approved"
            step.completed_at = utcnow()
            write_audit(db, None, "step_completed", "step_instance", step.id, request.id, {"step": step.name})
            _advance_or_complete(db, request)
    elif decision == "rejected":
        auth.status = "rejected"
        step.status = "rejected"
        step.completed_at = utcnow()
        request.status = "rejected"
        request.completed_at = utcnow()
        request.current_step_order = None
        write_audit(db, None, "request_rejected", "approval_request", request.id, request.id, {"comment": comment})
    elif decision == "changes_requested":
        request.status = "changes_requested"
        write_audit(
            db, None, "request_changes_requested", "approval_request", request.id, request.id, {"comment": comment}
        )
    else:
        raise ValidationFailedError(f"Unknown decision: {decision}")

    db.flush()
    return request


def cancel_request(db: Session, request_id: int, actor: User) -> ApprovalRequest:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise NotFoundError("Request not found")
    if actor.id != request.requester_id and actor.role != "admin":
        raise PermissionDeniedError("Only the requester or an admin can cancel a request")
    if request.status not in ("pending", "changes_requested"):
        raise ConflictError(f"Cannot cancel a request in status '{request.status}'")
    request.status = "cancelled"
    request.completed_at = utcnow()
    request.current_step_order = None
    write_audit(db, actor, "request_cancelled", "approval_request", request.id, request.id, {})
    db.flush()
    return request


def resubmit_request(db: Session, request_id: int, actor: User, payload: RequestResubmit) -> ApprovalRequest:
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise NotFoundError("Request not found")
    if actor.id != request.requester_id:
        raise PermissionDeniedError("Only the requester can resubmit")
    if request.status != "changes_requested":
        raise ConflictError("Only requests with changes requested can be resubmitted")

    if payload.title is not None:
        request.title = payload.title
    if payload.description is not None:
        request.description = payload.description
    if payload.amount is not None:
        request.amount = payload.amount
    if payload.data is not None:
        request.data = payload.data
    validate_request_data(request.template, float(request.amount) if request.amount is not None else None, request.data)

    for step in list(request.steps):
        db.delete(step)
    db.flush()
    request.status = "pending"
    request.completed_at = None
    write_audit(db, actor, "request_resubmitted", "approval_request", request.id, request.id, {})
    _route(db, request, request.template)
    db.flush()
    return request


# --- Visibility ---------------------------------------------------------------------------

def can_view_request(db: Session, user: User, request: ApprovalRequest) -> bool:
    """Requester, any resolved approver (incl. via delegation), and admins can view."""
    if user.role == "admin" or request.requester_id == user.id:
        return True
    approver_ids = {user.id} | active_delegator_ids(db, user)
    row = db.scalar(
        select(StepApprover.id)
        .where(StepApprover.request_id == request.id, StepApprover.approver_id.in_(approver_ids))
        .limit(1)
    )
    return row is not None


# --- Inbox ------------------------------------------------------------------------------

def inbox_for(db: Session, user: User) -> list[dict]:
    """Active steps awaiting `user` — their own authority plus delegated authority."""
    delegators = active_delegator_ids(db, user)
    allowed_ids = {user.id} | delegators
    rows = db.execute(
        select(StepApprover, StepInstance, ApprovalRequest)
        .join(StepInstance, StepApprover.step_instance_id == StepInstance.id)
        .join(ApprovalRequest, StepApprover.request_id == ApprovalRequest.id)
        .where(
            StepApprover.approver_id.in_(allowed_ids),
            StepApprover.status == "pending",
            StepInstance.status == "active",
            ApprovalRequest.status == "pending",
        )
        .order_by(ApprovalRequest.created_at.desc())
    ).all()
    items = []
    for approver_row, step, request in rows:
        items.append(
            {
                "request": request,
                "step": step,
                "on_behalf_of": approver_row.approver if approver_row.approver_id != user.id else None,
            }
        )
    return items


# --- Escalation -----------------------------------------------------------------------------

def run_escalation_sweep(db: Session) -> int:
    """Escalate overdue active steps: add the escalation target as an extra approver.

    An escalation approver's single approval completes the step even in 'all' mode.
    Returns the number of steps escalated.
    """
    now = utcnow()
    steps = db.scalars(
        select(StepInstance).where(StepInstance.status == "active", StepInstance.escalated.is_(False))
    ).all()
    count = 0
    for step in steps:
        if step.due_at is None or _aware(step.due_at) > now:
            continue
        tstep = step.template_step
        if tstep is None or (tstep.escalation_user_id is None and not tstep.escalation_role):
            continue
        targets: list[User] = []
        if tstep.escalation_user_id:
            user = db.get(User, tstep.escalation_user_id)
            if user and user.is_active:
                targets.append(user)
        if tstep.escalation_role:
            targets.extend(
                db.scalars(select(User).where(User.role == tstep.escalation_role, User.is_active.is_(True)))
            )
        existing = {a.approver_id for a in step.approvers}
        added = []
        for user in targets:
            if user.id not in existing:
                db.add(
                    StepApprover(
                        step_instance=step, request_id=step.request_id,
                        approver_id=user.id, is_escalation=True,
                    )
                )
                added.append(user.id)
        step.escalated = True
        count += 1
        write_audit(
            db, None, "step_escalated", "step_instance", step.id, step.request_id,
            {"step": step.name, "escalated_to": added, "due_at": step.due_at.isoformat() if step.due_at else None},
        )
    if count:
        db.flush()
    return count
