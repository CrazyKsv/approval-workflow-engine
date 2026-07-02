from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.exceptions import NotFoundError, PermissionDeniedError
from app.models import ApprovalRequest, AuditLog, StepApprover, User
from app.pagination import PageParams, paginate
from app.schemas import AuditOut, Page
from app.services import engine

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditOut])
def list_audit(
    request_id: int | None = Query(None),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Audit trail. Admins can browse everything; other users must scope to a
    request they can see (their own, or one they approve)."""
    query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if request_id is not None:
        request = db.get(ApprovalRequest, request_id)
        if request is None:
            raise NotFoundError("Request not found")
        if user.role != "admin" and request.requester_id != user.id:
            approver_ids = {user.id} | engine.active_delegator_ids(db, user)
            is_approver = db.scalar(
                select(StepApprover.id)
                .where(StepApprover.request_id == request_id, StepApprover.approver_id.in_(approver_ids))
                .limit(1)
            )
            if not is_approver:
                raise PermissionDeniedError("You do not have access to this request's audit trail")
        query = query.where(AuditLog.request_id == request_id)
    elif user.role != "admin":
        raise PermissionDeniedError("Provide request_id, or ask an admin for the global audit trail")
    items, total = paginate(db, query, params)
    return Page(items=items, total=total, page=params.page, size=params.size)
