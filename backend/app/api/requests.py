from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.exceptions import NotFoundError, PermissionDeniedError
from app.models import ApprovalRequest, User
from app.pagination import PageParams, paginate
from app.schemas import (
    DecisionCreate,
    InboxItemOut,
    Page,
    RequestCreate,
    RequestDetailOut,
    RequestOut,
    RequestResubmit,
    StatusFeedItemOut,
)
from app.services import engine

router = APIRouter(tags=["requests"])


@router.post("/requests", response_model=RequestDetailOut, status_code=201)
def submit_request(
    payload: RequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = engine.submit_request(db, user, payload)
    db.commit()
    db.refresh(request)
    return request


@router.get("/requests", response_model=Page[RequestOut])
def list_requests(
    status: str | None = Query(None),
    mine: bool = Query(True, description="Only my own requests (non-admins always get their own)"),
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
    if mine or user.role != "admin":
        query = query.where(ApprovalRequest.requester_id == user.id)
    if status:
        query = query.where(ApprovalRequest.status == status)
    items, total = paginate(db, query, params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/inbox", response_model=Page[InboxItemOut])
def inbox(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = engine.inbox_for(db, user)
    start = (params.page - 1) * params.size
    return Page(items=items[start : start + params.size], total=len(items), page=params.page, size=params.size)


@router.get("/inbox/status", response_model=list[StatusFeedItemOut])
def inbox_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Human-readable status of the caller's own requests, e.g.
    'approved by Mark Manager; waiting for finance approval'."""
    return engine.status_feed(db, user)


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = db.get(ApprovalRequest, request_id)
    if request is None:
        raise NotFoundError("Request not found")
    if not engine.can_view_request(db, user, request):
        raise PermissionDeniedError("You do not have access to this request")
    return request


@router.post("/requests/{request_id}/decision", response_model=RequestDetailOut)
def decide(
    request_id: int,
    payload: DecisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = engine.decide(db, request_id, user, payload.decision, payload.comment)
    db.commit()
    db.refresh(request)
    return request


@router.post("/requests/{request_id}/cancel", response_model=RequestDetailOut)
def cancel(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = engine.cancel_request(db, request_id, user)
    db.commit()
    db.refresh(request)
    return request


@router.post("/requests/{request_id}/resubmit", response_model=RequestDetailOut)
def resubmit(
    request_id: int,
    payload: RequestResubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request = engine.resubmit_request(db, request_id, user, payload)
    db.commit()
    db.refresh(request)
    return request
