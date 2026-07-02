"""Unit tests for the workflow engine: conditions, routing, quorum, delegation, escalation."""
from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import ConflictError, PermissionDeniedError, ValidationFailedError
from app.models import Delegation, utcnow
from app.schemas import RequestCreate, RequestResubmit
from app.services import engine


def submit(db, users, template_key="expense_template", requester_key="sarah", amount=500.0, data=None):
    template = users[template_key]
    payload = RequestCreate(
        template_id=template.id,
        title="Test request",
        amount=amount,
        data=data or {"expense_category": "hardware", "vendor": "Apple"},
    )
    request = engine.submit_request(db, users[requester_key], payload)
    db.commit()
    return request


# --- Conditions -----------------------------------------------------------------

@pytest.mark.parametrize(
    "condition,data,expected",
    [
        (None, {}, True),
        ({"field": "amount", "op": ">", "value": 1000}, {"amount": 1500}, True),
        ({"field": "amount", "op": ">", "value": 1000}, {"amount": 1000}, False),
        ({"field": "amount", "op": ">=", "value": 1000}, {"amount": "1000"}, True),
        ({"field": "amount", "op": "<", "value": 100}, {"amount": 5}, True),
        ({"field": "amount", "op": "<=", "value": 5}, {"amount": 6}, False),
        ({"field": "type", "op": "==", "value": "capex"}, {"type": "capex"}, True),
        ({"field": "type", "op": "!=", "value": "capex"}, {"type": "opex"}, True),
        ({"field": "dept", "op": "in", "value": ["eng", "ops"]}, {"dept": "eng"}, True),
        ({"field": "dept", "op": "not_in", "value": ["eng"]}, {"dept": "hr"}, True),
        ({"field": "title", "op": "contains", "value": "laptop"}, {"title": "new laptop"}, True),
        ({"field": "missing", "op": ">", "value": 1}, {}, False),
        ({"field": "amount", "op": ">", "value": 10}, {"amount": "not-a-number"}, False),
    ],
)
def test_evaluate_condition(condition, data, expected):
    assert engine.evaluate_condition(condition, data) is expected


# --- Routing ---------------------------------------------------------------------

def test_small_expense_skips_finance_and_approves(db, users):
    request = submit(db, users, amount=500.0)
    assert request.status == "pending"
    statuses = {s.name: s.status for s in request.steps}
    assert statuses["Manager approval"] == "active"
    assert statuses["Finance review"] == "skipped"

    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    assert request.status == "approved"
    assert request.completed_at is not None


def test_large_expense_routes_through_finance(db, users):
    request = submit(db, users, amount=2000.0)
    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    active = next(s for s in request.steps if s.status == "active")
    assert active.name == "Finance review"
    # 'any' mode: one finance member approval completes the request
    engine.decide(db, request.id, users["finance1"], "approved")
    db.commit()
    assert request.status == "approved"


def test_parallel_all_mode_requires_every_approver(db, users):
    request = submit(db, users, "purchase_template", amount=6000.0)
    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    active = next(s for s in request.steps if s.status == "active")
    assert active.name == "Finance review (all)"
    assert len(active.approvers) == 2

    engine.decide(db, request.id, users["finance1"], "approved")
    db.commit()
    assert active.status == "active", "step must stay active until all approve"
    engine.decide(db, request.id, users["finance2"], "approved")
    db.commit()
    # 6000 <= 10000 so the VP step is skipped and the request completes
    assert request.status == "approved"


def test_rejection_is_terminal(db, users):
    request = submit(db, users, amount=2000.0)
    engine.decide(db, request.id, users["manager"], "rejected", comment="No budget")
    db.commit()
    assert request.status == "rejected"
    with pytest.raises(ConflictError):
        engine.decide(db, request.id, users["finance1"], "approved")


def test_changes_requested_then_resubmit(db, users):
    request = submit(db, users, amount=2000.0)
    engine.decide(db, request.id, users["manager"], "changes_requested", comment="Split the invoice")
    db.commit()
    assert request.status == "changes_requested"

    engine.resubmit_request(db, request.id, users["sarah"], RequestResubmit(amount=800.0))
    db.commit()
    assert request.status == "pending"
    statuses = {s.name: s.status for s in request.steps}
    # New routing reflects the lower amount: finance is now skipped
    assert statuses["Finance review"] == "skipped"
    assert statuses["Manager approval"] == "active"


def test_non_approver_cannot_decide(db, users):
    request = submit(db, users, amount=500.0)
    with pytest.raises(PermissionDeniedError):
        engine.decide(db, request.id, users["mike"], "approved")


def test_missing_required_field_rejected(db, users):
    with pytest.raises(ValidationFailedError):
        engine.submit_request(
            db, users["sarah"],
            RequestCreate(template_id=users["expense_template"].id, title="No category", amount=100.0, data={}),
        )


def test_requester_excluded_from_own_approvers(db, users):
    request = submit(db, users, requester_key="manager", amount=500.0)
    active = next(s for s in request.steps if s.status == "active")
    approver_ids = {a.approver_id for a in active.approvers}
    assert users["manager"].id not in approver_ids
    assert users["manager2"].id in approver_ids


# --- Delegation ---------------------------------------------------------------------

def _delegate(db, delegator, delegate, hours=24):
    now = utcnow()
    db.add(
        Delegation(
            delegator_id=delegator.id, delegate_id=delegate.id,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=hours),
        )
    )
    db.commit()


def test_delegate_can_decide_on_behalf_of_delegator(db, users):
    request = submit(db, users, amount=500.0)
    _delegate(db, users["manager"], users["mike"])
    # manager2 is also a pending approver; mike acts on manager's authority only
    engine.decide(db, request.id, users["mike"], "approved", comment="Approved while Mark is away")
    db.commit()
    assert request.status == "approved"
    decision = request.decisions[0]
    assert decision.acting_user_id == users["mike"].id
    assert decision.approver_id == users["manager"].id


def test_delegated_items_appear_in_inbox(db, users):
    request = submit(db, users, amount=500.0)
    _delegate(db, users["manager"], users["mike"])
    items = engine.inbox_for(db, users["mike"])
    assert len(items) == 1
    assert items[0]["request"].id == request.id
    assert items[0]["on_behalf_of"].id == users["manager"].id


def test_expired_delegation_grants_nothing(db, users):
    request = submit(db, users, amount=500.0)
    now = utcnow()
    db.add(
        Delegation(
            delegator_id=users["manager"].id, delegate_id=users["mike"].id,
            starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1),
        )
    )
    db.commit()
    with pytest.raises(PermissionDeniedError):
        engine.decide(db, request.id, users["mike"], "approved")


# --- Escalation ------------------------------------------------------------------------

def test_overdue_step_escalates_and_escalation_overrides_quorum(db, users):
    request = submit(db, users, "purchase_template", amount=6000.0)
    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    step = next(s for s in request.steps if s.status == "active")
    assert step.name == "Finance review (all)"

    step.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    escalated = engine.run_escalation_sweep(db)
    db.commit()
    assert escalated == 1
    assert step.escalated is True
    escalation_rows = [a for a in step.approvers if a.is_escalation]
    assert [a.approver.role for a in escalation_rows] == ["vp"]

    # VP's escalation approval completes the step even though mode is 'all'
    engine.decide(db, request.id, users["vp"], "approved")
    db.commit()
    assert step.status == "approved"
    assert request.status == "approved"


def test_sweep_ignores_steps_within_sla(db, users):
    request = submit(db, users, amount=500.0)
    assert engine.run_escalation_sweep(db) == 0
    step = next(s for s in request.steps if s.status == "active")
    assert step.escalated is False
