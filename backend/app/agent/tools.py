"""Agent tool definitions and executors.

Every tool executes through the same service layer as the REST API, under the
authenticated user's identity — RBAC and audit apply identically. Mutating tools
enforce a server-side confirmation contract: called without confirmed=true they
return status=confirmation_required with a human-readable summary the model must
present to the user before retrying with confirmed=true.
"""
import logging
from datetime import datetime
from typing import Callable

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import DomainError, NotFoundError, ValidationFailedError
from app.models import ApprovalRequest, AuditLog, Group, User, WorkflowTemplate
from app.schemas import DelegationCreate, RequestCreate, TemplateCreate
from app.services import delegations as delegation_service
from app.services import engine
from app.services import templates as template_service

logger = logging.getLogger("agent.tools")

MUTATING_TOOLS = {"submit_request", "decide_request", "create_delegation", "create_workflow_template"}


# --- Serialization helpers ---------------------------------------------------

def _user_dict(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


def _template_dict(t: WorkflowTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "is_active": t.is_active,
        "fields": t.fields or [],
        "steps": [
            {
                "step_order": s.step_order,
                "name": s.name,
                "approver_type": s.approver_type,
                "approver_user_id": s.approver_user_id,
                "approver_group_id": s.approver_group_id,
                "approver_role": s.approver_role,
                "approval_mode": s.approval_mode,
                "condition": s.condition,
                "sla_hours": s.sla_hours,
            }
            for s in t.steps
        ],
    }


def _request_dict(r: ApprovalRequest, include_steps: bool = False) -> dict:
    active = next((s for s in r.steps if s.status == "active"), None)
    out = {
        "id": r.id,
        "title": r.title,
        "template_id": r.template_id,
        "requester": _user_dict(r.requester),
        "amount": float(r.amount) if r.amount is not None else None,
        "data": r.data or {},
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "current_step": active.name if active else None,
        "next_approvers": [_user_dict(a.approver) for a in active.approvers if a.status == "pending"]
        if active
        else [],
    }
    if include_steps:
        out["steps"] = [
            {
                "step_order": s.step_order,
                "name": s.name,
                "status": s.status,
                "approval_mode": s.approval_mode,
                "due_at": s.due_at.isoformat() if s.due_at else None,
                "escalated": s.escalated,
                "approvers": [
                    {"user": _user_dict(a.approver), "status": a.status, "is_escalation": a.is_escalation}
                    for a in s.approvers
                ],
            }
            for s in sorted(r.steps, key=lambda s: s.step_order)
        ]
        out["decisions"] = [
            {
                "decision": d.decision,
                "comment": d.comment,
                "approver": _user_dict(d.approver),
                "acting_user": _user_dict(d.acting_user),
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in r.decisions
        ]
    return out


def _needs_confirmation(args: dict, summary: str) -> dict | None:
    if args.get("confirmed") is True:
        return None
    return {
        "status": "confirmation_required",
        "action_summary": summary,
        "instruction": "Present this summary to the user and ask for explicit confirmation. "
        "Only after the user confirms, call this tool again with confirmed=true.",
    }


# --- Tool executors ------------------------------------------------------------

def tool_list_workflow_templates(db: Session, user: User, args: dict) -> dict:
    templates = db.scalars(
        select(WorkflowTemplate).where(WorkflowTemplate.is_active.is_(True)).order_by(WorkflowTemplate.id)
    ).all()
    return {"templates": [_template_dict(t) for t in templates]}


def tool_list_users_and_groups(db: Session, user: User, args: dict) -> dict:
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id)).all()
    groups = db.scalars(select(Group).order_by(Group.id)).all()
    return {
        "users": [_user_dict(u) for u in users],
        "groups": [
            {"id": g.id, "name": g.name, "member_ids": [m.id for m in g.members]} for g in groups
        ],
    }


def tool_submit_request(db: Session, user: User, args: dict) -> dict:
    template = db.get(WorkflowTemplate, args.get("template_id"))
    if template is None:
        raise NotFoundError("Workflow template not found — use list_workflow_templates first")
    payload = RequestCreate(
        template_id=template.id,
        title=args.get("title") or "",
        description=args.get("description"),
        amount=args.get("amount"),
        data=args.get("data") or {},
    )
    # Validate before asking for confirmation so the model gathers missing fields first.
    engine.validate_request_data(template, payload.amount, payload.data)
    confirmation = _needs_confirmation(
        args,
        f"Submit a '{template.name}' request titled '{payload.title}'"
        + (f" for ${payload.amount:,.2f}" if payload.amount is not None else "")
        + f" on behalf of {user.name}.",
    )
    if confirmation:
        return confirmation
    request = engine.submit_request(db, user, payload)
    db.commit()
    return {"status": "submitted", "request": _request_dict(request)}


def tool_get_pending_approvals(db: Session, user: User, args: dict) -> dict:
    items = engine.inbox_for(db, user)
    return {
        "pending_approvals": [
            {
                "request": _request_dict(item["request"]),
                "step": item["step"].name,
                "on_behalf_of": _user_dict(item["on_behalf_of"]) if item["on_behalf_of"] else None,
            }
            for item in items
        ]
    }


def tool_get_my_requests(db: Session, user: User, args: dict) -> dict:
    requests = db.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.requester_id == user.id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(25)
    ).all()
    return {"requests": [_request_dict(r) for r in requests]}


def tool_get_request_status(db: Session, user: User, args: dict) -> dict:
    """Status feed for the user's own requests, as human-readable messages."""
    items = engine.status_feed(db, user)
    return {
        "request_status": [
            {
                "request_id": item["request"].id,
                "title": item["request"].title,
                "status": item["request"].status,
                "message": f"Request #{item['request'].id} '{item['request'].title}' — {item['message']}",
            }
            for item in items
        ]
    }


def tool_get_request_details(db: Session, user: User, args: dict) -> dict:
    request = db.get(ApprovalRequest, args.get("request_id"))
    if request is None:
        raise NotFoundError("Request not found")
    if not engine.can_view_request(db, user, request):
        raise DomainError("You do not have access to this request")
    return {"request": _request_dict(request, include_steps=True)}


def tool_decide_request(db: Session, user: User, args: dict) -> dict:
    request = db.get(ApprovalRequest, args.get("request_id"))
    if request is None:
        raise NotFoundError("Request not found")
    decision = args.get("decision")
    if decision not in ("approved", "rejected", "changes_requested"):
        raise ValidationFailedError("decision must be approved, rejected or changes_requested")
    confirmation = _needs_confirmation(
        args,
        f"Record decision '{decision}' on request #{request.id} '{request.title}' "
        f"(requested by {request.requester.name})"
        + (f" with comment: {args.get('comment')}" if args.get("comment") else "")
        + ".",
    )
    if confirmation:
        return confirmation
    request = engine.decide(db, request.id, user, decision, args.get("comment"))
    db.commit()
    return {"status": "decision_recorded", "request": _request_dict(request)}


def tool_create_delegation(db: Session, user: User, args: dict) -> dict:
    delegate = db.get(User, args.get("delegate_id")) if args.get("delegate_id") else None
    if delegate is None:
        raise NotFoundError("Delegate user not found — use list_users_and_groups to find their id")
    try:
        starts_at = datetime.fromisoformat(args["starts_at"])
        ends_at = datetime.fromisoformat(args["ends_at"])
    except (KeyError, ValueError):
        raise ValidationFailedError("starts_at and ends_at must be ISO 8601 datetimes")
    confirmation = _needs_confirmation(
        args,
        f"Delegate {user.name}'s approval authority to {delegate.name} "
        f"from {starts_at.isoformat()} to {ends_at.isoformat()}.",
    )
    if confirmation:
        return confirmation
    delegation = delegation_service.create_delegation(
        db, user,
        DelegationCreate(delegate_id=delegate.id, starts_at=starts_at, ends_at=ends_at, reason=args.get("reason")),
    )
    db.commit()
    return {
        "status": "delegation_created",
        "delegation": {
            "id": delegation.id,
            "delegate": _user_dict(delegate),
            "starts_at": delegation.starts_at.isoformat(),
            "ends_at": delegation.ends_at.isoformat(),
        },
    }


def tool_create_workflow_template(db: Session, user: User, args: dict) -> dict:
    try:
        payload = TemplateCreate(
            name=args.get("name") or "",
            description=args.get("description"),
            category=args.get("category"),
            fields=args.get("fields") or [],
            steps=args.get("steps") or [],
        )
    except ValidationError as exc:
        raise ValidationFailedError(f"Invalid template definition: {exc.errors()}")
    steps_summary = "; ".join(
        f"{s.step_order}. {s.name} ({s.approver_type}"
        + (f"={s.approver_role}" if s.approver_role else "")
        + (f", if {s.condition.field} {s.condition.op} {s.condition.value}" if s.condition else "")
        + ")"
        for s in payload.steps
    )
    confirmation = _needs_confirmation(
        args, f"Create workflow template '{payload.name}' with steps: {steps_summary}."
    )
    if confirmation:
        return confirmation
    template = template_service.create_template(db, user, payload)
    db.commit()
    return {"status": "template_created", "template": _template_dict(template)}


def tool_get_audit_history(db: Session, user: User, args: dict) -> dict:
    request = db.get(ApprovalRequest, args.get("request_id"))
    if request is None:
        raise NotFoundError("Request not found")
    if not engine.can_view_request(db, user, request):
        raise DomainError("You do not have access to this request's audit trail")
    entries = db.scalars(
        select(AuditLog).where(AuditLog.request_id == request.id).order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    return {
        "audit": [
            {
                "action": e.action,
                "actor": _user_dict(e.actor) if e.actor else None,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]
    }


TOOL_EXECUTORS: dict[str, Callable[[Session, User, dict], dict]] = {
    "list_workflow_templates": tool_list_workflow_templates,
    "list_users_and_groups": tool_list_users_and_groups,
    "submit_request": tool_submit_request,
    "get_pending_approvals": tool_get_pending_approvals,
    "get_my_requests": tool_get_my_requests,
    "get_request_status": tool_get_request_status,
    "get_request_details": tool_get_request_details,
    "decide_request": tool_decide_request,
    "create_delegation": tool_create_delegation,
    "create_workflow_template": tool_create_workflow_template,
    "get_audit_history": tool_get_audit_history,
}


def run_tool(db: Session, user: User, name: str, args: dict) -> dict:
    """Execute a tool; domain errors become structured results the model can relay."""
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"error": "unknown_tool", "message": f"No tool named '{name}'"}
    try:
        return executor(db, user, args)
    except DomainError as exc:
        db.rollback()
        return {"error": type(exc).__name__, "message": exc.message}
    except ValidationError as exc:
        db.rollback()
        return {"error": "ValidationError", "message": str(exc)}
    except Exception:
        db.rollback()
        logger.exception("Tool %s failed", name)
        return {"error": "internal_error", "message": "The tool failed unexpectedly. Try again or rephrase."}


# --- OpenAI tool schemas ---------------------------------------------------------

_CONFIRMED_PARAM = {
    "type": "boolean",
    "description": "Must be true to execute. Omit on the first call to receive a confirmation "
    "summary to present to the user.",
}

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_workflow_templates",
            "description": "List active workflow templates with their input fields and approval steps. "
            "Use this to pick the right workflow and learn which fields are required.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_users_and_groups",
            "description": "List users (with ids, emails, roles) and approver groups. Use to resolve names to ids.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_request",
            "description": "Submit an approval request. Requires confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "amount": {"type": "number", "description": "Monetary amount if applicable"},
                    "data": {"type": "object", "description": "Values for the template's declared fields"},
                    "confirmed": _CONFIRMED_PARAM,
                },
                "required": ["template_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pending_approvals",
            "description": "List approvals waiting on the current user, including ones delegated to them.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_requests",
            "description": "List the current user's own submitted requests and their statuses.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_request_status",
            "description": "Status feed for the current user's own requests as ready-to-relay messages, "
            "e.g. \"Request #7 'Laptop' — approved by Mark Manager; waiting for finance approval\". "
            "Use this when the user asks about the status/progress of their requests (their 'inbox status').",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_request_details",
            "description": "Full detail of one request: steps, approvers, decisions. Use before deciding.",
            "parameters": {
                "type": "object",
                "properties": {"request_id": {"type": "integer"}},
                "required": ["request_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decide_request",
            "description": "Approve, reject, or request changes on a request the user is an approver for. "
            "Requires confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["approved", "rejected", "changes_requested"]},
                    "comment": {"type": "string"},
                    "confirmed": _CONFIRMED_PARAM,
                },
                "required": ["request_id", "decision"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_delegation",
            "description": "Temporarily delegate the current user's approval authority to another user. "
            "Role rules (server-enforced): manager may delegate to manager/finance/vp; finance to "
            "finance/vp; vp to finance only; employee and admin cannot delegate. "
            "Requires confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "delegate_id": {"type": "integer"},
                    "starts_at": {"type": "string", "description": "ISO 8601 datetime"},
                    "ends_at": {"type": "string", "description": "ISO 8601 datetime"},
                    "reason": {"type": "string"},
                    "confirmed": _CONFIRMED_PARAM,
                },
                "required": ["delegate_id", "starts_at", "ends_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_workflow_template",
            "description": "Create a new workflow template (admin only). Steps route by approver_type "
            "user/group/role; optional condition per step for conditional routing "
            "(ops: ==, !=, >, >=, <, <=, in, not_in, contains); approval_mode 'any' or 'all'; "
            "optional sla_hours + escalation. Requires confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "label": {"type": "string"},
                                "type": {"type": "string", "enum": ["string", "number", "date", "boolean"]},
                                "required": {"type": "boolean"},
                            },
                            "required": ["name", "label"],
                        },
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_order": {"type": "integer"},
                                "name": {"type": "string"},
                                "approver_type": {"type": "string", "enum": ["user", "group", "role"]},
                                "approver_user_id": {"type": "integer"},
                                "approver_group_id": {"type": "integer"},
                                "approver_role": {
                                    "type": "string",
                                    "enum": ["admin", "manager", "finance", "vp", "employee"],
                                },
                                "approval_mode": {"type": "string", "enum": ["any", "all"]},
                                "condition": {
                                    "type": "object",
                                    "properties": {
                                        "field": {"type": "string"},
                                        "op": {"type": "string"},
                                        "value": {},
                                    },
                                    "required": ["field", "op", "value"],
                                },
                                "sla_hours": {"type": "integer"},
                                "escalation_user_id": {"type": "integer"},
                                "escalation_role": {"type": "string"},
                            },
                            "required": ["step_order", "name", "approver_type"],
                        },
                    },
                    "confirmed": _CONFIRMED_PARAM,
                },
                "required": ["name", "steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audit_history",
            "description": "Chronological audit trail for a request: submissions, routing, decisions, escalations.",
            "parameters": {
                "type": "object",
                "properties": {"request_id": {"type": "integer"}},
                "required": ["request_id"],
            },
        },
    },
]
