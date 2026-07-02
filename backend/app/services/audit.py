from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    request_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=request_id,
        details=details or {},
    )
    db.add(entry)
    return entry
