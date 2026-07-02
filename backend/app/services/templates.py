from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models import Group, TemplateStep, User, WorkflowTemplate
from app.schemas import ROLES, TemplateCreate
from app.services.audit import write_audit


def create_template(db: Session, actor: User, payload: TemplateCreate) -> WorkflowTemplate:
    if actor.role != "admin":
        raise PermissionDeniedError("Only admins can create workflow templates")
    _validate_steps(db, payload)

    template = WorkflowTemplate(
        name=payload.name,
        description=payload.description,
        category=payload.category,
        fields=[f.model_dump() for f in payload.fields],
        created_by_id=actor.id,
    )
    db.add(template)
    db.flush()
    for step in payload.steps:
        db.add(
            TemplateStep(
                template_id=template.id,
                step_order=step.step_order,
                name=step.name,
                approver_type=step.approver_type,
                approver_user_id=step.approver_user_id,
                approver_group_id=step.approver_group_id,
                approver_role=step.approver_role,
                approval_mode=step.approval_mode,
                condition=step.condition.model_dump() if step.condition else None,
                sla_hours=step.sla_hours,
                escalation_user_id=step.escalation_user_id,
                escalation_role=step.escalation_role,
            )
        )
    write_audit(db, actor, "template_created", "workflow_template", template.id, None, {"name": template.name})
    db.flush()
    db.refresh(template)
    return template


def _validate_steps(db: Session, payload: TemplateCreate) -> None:
    orders = [s.step_order for s in payload.steps]
    if len(orders) != len(set(orders)):
        raise ValidationFailedError("step_order values must be unique")
    field_names = {f.name for f in payload.fields} | {"amount"}
    for step in payload.steps:
        if step.approver_type == "user":
            if not step.approver_user_id or db.get(User, step.approver_user_id) is None:
                raise ValidationFailedError(f"Step '{step.name}': approver_user_id is missing or unknown")
        elif step.approver_type == "group":
            if not step.approver_group_id or db.get(Group, step.approver_group_id) is None:
                raise ValidationFailedError(f"Step '{step.name}': approver_group_id is missing or unknown")
        elif step.approver_type == "role":
            if step.approver_role not in ROLES:
                raise ValidationFailedError(f"Step '{step.name}': approver_role must be one of {sorted(ROLES)}")
        if step.condition and step.condition.field not in field_names:
            raise ValidationFailedError(
                f"Step '{step.name}': condition references unknown field '{step.condition.field}'"
            )
        if step.escalation_role and step.escalation_role not in ROLES:
            raise ValidationFailedError(f"Step '{step.name}': unknown escalation_role")
        if step.escalation_user_id and db.get(User, step.escalation_user_id) is None:
            raise ValidationFailedError(f"Step '{step.name}': unknown escalation_user_id")


def set_template_active(db: Session, actor: User, template_id: int, is_active: bool) -> WorkflowTemplate:
    if actor.role != "admin":
        raise PermissionDeniedError("Only admins can update workflow templates")
    template = db.get(WorkflowTemplate, template_id)
    if template is None:
        raise NotFoundError("Workflow template not found")
    template.is_active = is_active
    write_audit(
        db, actor, "template_updated", "workflow_template", template.id, None, {"is_active": is_active}
    )
    db.flush()
    return template


def list_templates(db: Session, include_inactive: bool = False):
    query = select(WorkflowTemplate).order_by(WorkflowTemplate.id)
    if not include_inactive:
        query = query.where(WorkflowTemplate.is_active.is_(True))
    return query
