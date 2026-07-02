from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Group, User
from app.pagination import PageParams, paginate
from app.schemas import GroupOut, Page, UserOut

router = APIRouter(tags=["directory"])


@router.get("/users", response_model=Page[UserOut])
def list_users(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    items, total = paginate(db, select(User).where(User.is_active.is_(True)).order_by(User.id), params)
    return Page(items=items, total=total, page=params.page, size=params.size)


@router.get("/groups", response_model=Page[GroupOut])
def list_groups(
    params: PageParams = Depends(),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    items, total = paginate(db, select(Group).order_by(Group.id), params)
    return Page(items=items, total=total, page=params.page, size=params.size)
