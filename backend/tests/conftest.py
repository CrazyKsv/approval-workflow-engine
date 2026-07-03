import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["ENABLE_ESCALATION_SWEEP"] = "false"
os.environ["KIMI_API_KEY"] = "test-key"

import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Group, TemplateStep, User, WorkflowTemplate
from app.security import create_access_token

# One cheap bcrypt hash shared by all test users (default rounds are too slow for tests).
PW_HASH = bcrypt.hashpw(b"password123", bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def users(db):
    """Directory of demo users, the Finance group, and two templates."""
    def make(email, name, role):
        user = User(email=email, name=name, role=role, password_hash=PW_HASH)
        db.add(user)
        return user

    directory = {
        "admin": make("admin@acme.com", "Alice Admin", "admin"),
        "manager": make("manager@acme.com", "Mark Manager", "manager"),
        "manager2": make("manager2@acme.com", "Mel Manager", "manager"),
        "finance1": make("finance1@acme.com", "Fiona Finance", "finance"),
        "finance2": make("finance2@acme.com", "Frank Finance", "finance"),
        "vp": make("vp@acme.com", "Victoria VP", "vp"),
        "sarah": make("sarah@acme.com", "Sarah Employee", "employee"),
        "mike": make("mike@acme.com", "Mike Employee", "employee"),
    }
    db.flush()

    finance_group = Group(name="Finance Team")
    finance_group.members = [directory["finance1"], directory["finance2"]]
    db.add(finance_group)
    db.flush()
    directory["finance_group"] = finance_group

    # The clarified standard chain: manager -> finance -> vp (role steps, no conditions).
    expense = WorkflowTemplate(
        name="Expense Report",
        category="finance",
        fields=[
            {"name": "amount", "label": "Amount", "type": "number", "required": True},
            {"name": "expense_category", "label": "Category", "type": "string", "required": True},
        ],
        created_by_id=directory["admin"].id,
    )
    db.add(expense)
    db.flush()
    db.add_all(
        [
            TemplateStep(
                template_id=expense.id, step_order=1, name="Manager approval",
                approver_type="role", approver_role="manager",
                sla_hours=48, escalation_role="vp",
            ),
            TemplateStep(
                template_id=expense.id, step_order=2, name="Finance review",
                approver_type="role", approver_role="finance", approval_mode="any",
            ),
            TemplateStep(
                template_id=expense.id, step_order=3, name="VP sign-off",
                approver_type="role", approver_role="vp",
            ),
        ]
    )

    purchase = WorkflowTemplate(
        name="Purchase Order",
        category="procurement",
        fields=[
            {"name": "amount", "label": "Amount", "type": "number", "required": True},
            {"name": "vendor", "label": "Vendor", "type": "string", "required": True},
        ],
        created_by_id=directory["admin"].id,
    )
    db.add(purchase)
    db.flush()
    db.add_all(
        [
            TemplateStep(
                template_id=purchase.id, step_order=1, name="Manager approval",
                approver_type="role", approver_role="manager",
            ),
            TemplateStep(
                template_id=purchase.id, step_order=2, name="Finance review (all)",
                approver_type="group", approver_group_id=finance_group.id, approval_mode="all",
                condition={"field": "amount", "op": ">", "value": 5000},
                sla_hours=24, escalation_role="vp",
            ),
            TemplateStep(
                template_id=purchase.id, step_order=3, name="VP sign-off",
                approver_type="role", approver_role="vp",
                condition={"field": "amount", "op": ">", "value": 10000},
            ),
        ]
    )
    db.commit()
    directory["expense_template"] = expense
    directory["purchase_template"] = purchase
    return directory


@pytest.fixture()
def client(db):
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}
