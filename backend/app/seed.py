"""Idempotent demo seed: users and the Finance group.

Workflow templates are no longer seeded here — they are declared in
``app/workflow_templates.yaml`` and loaded on startup by
``app.services.template_loader`` (create-if-missing by name), so templates are
configurable and onboardable by PR, admin UI, or the AI assistant.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Group, User
from app.security import hash_password

logger = logging.getLogger("seed")

DEMO_PASSWORD = "password123"

USERS = [
    ("admin@acme.com", "Alice Admin", "admin"),
    ("manager@acme.com", "Mark Manager", "manager"),
    ("finance1@acme.com", "Fiona Finance", "finance"),
    ("finance2@acme.com", "Frank Finance", "finance"),
    ("vp@acme.com", "Victoria VP", "vp"),
    ("sarah@acme.com", "Sarah Employee", "employee"),
    ("mike@acme.com", "Mike Employee", "employee"),
]


def seed(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        logger.info("Seed skipped: users already exist")
        return

    users: dict[str, User] = {}
    for email, name, role in USERS:
        user = User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        users[email] = user
    db.flush()

    finance_group = Group(name="Finance Team", description="Reviews spend requests")
    finance_group.members = [users["finance1@acme.com"], users["finance2@acme.com"]]
    db.add(finance_group)

    db.commit()
    logger.info("Seeded %d users and 1 group (templates load from the YAML catalog)", len(USERS))
