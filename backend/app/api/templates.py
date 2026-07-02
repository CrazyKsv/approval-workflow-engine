from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.exceptions import NotFoundError
from app.models import User, WorkflowTemplate
from app.pagination import PageParams, paginate
from app.schemas import Page, TemplateCreate, TemplateOut, TemplateUpdate
from app.services import templates as template_service

router = APIRouter(prefix="/templates", tags=["workflow-admin"])


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    template = template_service.create_template(db, user, payload)
    db.commit()
    db.refresh(template)
    return template


@router.get("", response_model=Page[TemplateOut])
def list_templates(
    include_inactive: bool = False,
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    include_inactive = include_inactive and user.role == "admin"
    items, total = paginate(db, template_service.list_templates(db, include_inactive), params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    template = db.get(WorkflowTemplate, template_id)
    if template is None:
        raise NotFoundError("Workflow template not found")
    return template


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    template = template_service.set_template_active(db, user, template_id, payload.is_active)
    db.commit()
    db.refresh(template)
    return template
