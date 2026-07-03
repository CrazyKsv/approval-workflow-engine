"""Idempotent demo seed: users, groups, and three workflow templates."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Group, TemplateStep, User, WorkflowTemplate
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
    db.flush()

    admin = users["admin@acme.com"]

    def add_chain_steps(template_id: int) -> None:
        """The clarified standard flow: manager -> finance -> vp. The engine skips the
        step matching the requester's own role (a manager's request starts at finance)."""
        db.add_all(
            [
                TemplateStep(
                    template_id=template_id, step_order=1, name="Manager approval",
                    approver_type="role", approver_role="manager", sla_hours=48, escalation_role="vp",
                ),
                TemplateStep(
                    template_id=template_id, step_order=2, name="Finance review",
                    approver_type="role", approver_role="finance", approval_mode="any", sla_hours=48,
                    escalation_role="vp",
                ),
                TemplateStep(
                    template_id=template_id, step_order=3, name="VP sign-off",
                    approver_type="role", approver_role="vp", sla_hours=72,
                ),
            ]
        )

    expense = WorkflowTemplate(
        name="Expense Report",
        description="Expense reimbursement. Standard flow: manager -> finance -> VP.",
        category="finance",
        fields=[
            {"name": "amount", "label": "Amount (USD)", "type": "number", "required": True},
            {"name": "expense_category", "label": "Expense category", "type": "string", "required": True},
        ],
        created_by_id=admin.id,
    )
    db.add(expense)
    db.flush()
    add_chain_steps(expense.id)

    purchase = WorkflowTemplate(
        name="Purchase Order",
        description="Equipment/software purchases. Standard flow: manager -> finance -> VP.",
        category="procurement",
        fields=[
            {"name": "amount", "label": "Amount (USD)", "type": "number", "required": True},
            {"name": "vendor", "label": "Vendor", "type": "string", "required": True},
            {"name": "justification", "label": "Business justification", "type": "string", "required": False},
        ],
        created_by_id=admin.id,
    )
    db.add(purchase)
    db.flush()
    add_chain_steps(purchase.id)

    timeoff = WorkflowTemplate(
        name="Time Off Request",
        description="Vacation and leave requests. Standard flow: manager -> finance -> VP.",
        category="hr",
        fields=[
            {"name": "start_date", "label": "Start date", "type": "date", "required": True},
            {"name": "end_date", "label": "End date", "type": "date", "required": True},
            {"name": "reason", "label": "Reason", "type": "string", "required": False},
        ],
        created_by_id=admin.id,
    )
    db.add(timeoff)
    db.flush()
    add_chain_steps(timeoff.id)

    db.commit()
    logger.info("Seeded %d users, 1 group, 3 workflow templates", len(USERS))
