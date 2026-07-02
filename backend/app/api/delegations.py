from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.pagination import PageParams, paginate
from app.schemas import DelegationCreate, DelegationOut, Page
from app.services import delegations as delegation_service

router = APIRouter(prefix="/delegations", tags=["delegations"])


@router.post("", response_model=DelegationOut, status_code=201)
def create_delegation(
    payload: DelegationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delegation = delegation_service.create_delegation(db, user, payload)
    db.commit()
    db.refresh(delegation)
    return delegation


@router.get("", response_model=Page[DelegationOut])
def list_delegations(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = paginate(db, delegation_service.list_delegations_for(db, user), params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.delete("/{delegation_id}", response_model=DelegationOut)
def revoke_delegation(
    delegation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delegation = delegation_service.revoke_delegation(db, user, delegation_id)
    db.commit()
    db.refresh(delegation)
    return delegation
