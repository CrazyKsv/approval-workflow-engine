from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.exceptions import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models import Delegation, User
from app.schemas import DelegationCreate
from app.services.audit import write_audit


def create_delegation(db: Session, actor: User, payload: DelegationCreate) -> Delegation:
    if payload.delegate_id == actor.id:
        raise ValidationFailedError("Cannot delegate to yourself")
    delegate = db.get(User, payload.delegate_id)
    if delegate is None or not delegate.is_active:
        raise NotFoundError("Delegate user not found or inactive")
    if payload.ends_at <= payload.starts_at:
        raise ValidationFailedError("ends_at must be after starts_at")

    delegation = Delegation(
        delegator_id=actor.id,
        delegate_id=payload.delegate_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        reason=payload.reason,
    )
    db.add(delegation)
    db.flush()
    write_audit(
        db, actor, "delegation_created", "delegation", delegation.id, None,
        {
            "delegate_id": payload.delegate_id,
            "starts_at": payload.starts_at.isoformat(),
            "ends_at": payload.ends_at.isoformat(),
            "reason": payload.reason,
        },
    )
    return delegation


def revoke_delegation(db: Session, actor: User, delegation_id: int) -> Delegation:
    delegation = db.get(Delegation, delegation_id)
    if delegation is None:
        raise NotFoundError("Delegation not found")
    if delegation.delegator_id != actor.id and actor.role != "admin":
        raise PermissionDeniedError("Only the delegator or an admin can revoke a delegation")
    delegation.is_active = False
    write_audit(db, actor, "delegation_revoked", "delegation", delegation.id, None, {})
    db.flush()
    return delegation


def list_delegations_for(db: Session, user: User):
    return (
        select(Delegation)
        .where(or_(Delegation.delegator_id == user.id, Delegation.delegate_id == user.id))
        .order_by(Delegation.created_at.desc())
    )
