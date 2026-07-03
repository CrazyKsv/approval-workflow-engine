"""Unit tests for the workflow engine: chain routing, requester-role skip, conditions,
quorum, delegation rules, self-approval block, escalation, status feed."""
from datetime import datetime, timedelta, timezone

import pytest

from app.exceptions import ConflictError, PermissionDeniedError, ValidationFailedError
from app.models import Delegation, utcnow
from app.schemas import DelegationCreate, RequestCreate, RequestResubmit
from app.services import engine
from app.services.delegations import create_delegation


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


def approve_chain(db, request, *deciders):
    for user in deciders:
        engine.decide(db, request.id, user, "approved")
        db.commit()


# --- Conditions (still supported for custom templates) -----------------------------

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


# --- Standard chain routing ---------------------------------------------------------

def test_employee_request_walks_full_chain(db, users):
    """employee -> manager -> finance -> vp: every step must be approved in order."""
    request = submit(db, users, amount=500.0)
    assert request.status == "pending"
    assert {s.name: s.status for s in request.steps} == {
        "Manager approval": "active",
        "Finance review": "pending",
        "VP sign-off": "pending",
    }

    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    assert next(s for s in request.steps if s.name == "Finance review").status == "active"

    engine.decide(db, request.id, users["finance1"], "approved")
    db.commit()
    assert next(s for s in request.steps if s.name == "VP sign-off").status == "active"

    engine.decide(db, request.id, users["vp"], "approved")
    db.commit()
    assert request.status == "approved"
    assert request.completed_at is not None


def test_manager_request_skips_manager_step(db, users):
    """A manager's request goes straight to finance -> vp (own-role step skipped)."""
    request = submit(db, users, requester_key="manager", amount=800.0)
    statuses = {s.name: s.status for s in request.steps}
    assert statuses["Manager approval"] == "skipped"
    assert statuses["Finance review"] == "active"
    assert statuses["VP sign-off"] == "pending"


def test_finance_request_skips_finance_step(db, users):
    request = submit(db, users, requester_key="finance1", amount=800.0)
    statuses = {s.name: s.status for s in request.steps}
    assert statuses["Manager approval"] == "active"
    assert statuses["Finance review"] == "skipped"
    assert statuses["VP sign-off"] == "pending"


def test_vp_request_skips_vp_step(db, users):
    request = submit(db, users, requester_key="vp", amount=800.0)
    statuses = {s.name: s.status for s in request.steps}
    assert statuses["Manager approval"] == "active"
    assert statuses["Finance review"] == "pending"
    assert statuses["VP sign-off"] == "skipped"
    approve_chain(db, request, users["manager"], users["finance1"])
    assert request.status == "approved"


def test_admin_cannot_submit_requests(db, users):
    with pytest.raises(PermissionDeniedError):
        submit(db, users, requester_key="admin", amount=100.0)


# --- Conditional custom template still works ----------------------------------------

def test_conditional_template_routes_by_amount(db, users):
    """purchase_template keeps per-step conditions: finance only > $5,000, vp only > $10,000."""
    request = submit(db, users, "purchase_template", amount=4000.0)
    statuses = {s.name: s.status for s in request.steps}
    assert statuses["Finance review (all)"] == "skipped"
    assert statuses["VP sign-off"] == "skipped"
    engine.decide(db, request.id, users["manager"], "approved")
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
    assert request.status == "approved"


# --- Decisions ------------------------------------------------------------------------

def test_rejection_is_terminal(db, users):
    request = submit(db, users, amount=2000.0)
    engine.decide(db, request.id, users["manager"], "rejected", comment="No budget")
    db.commit()
    assert request.status == "rejected"
    with pytest.raises(ConflictError):
        engine.decide(db, request.id, users["finance1"], "approved")


def test_changes_requested_then_resubmit_restarts_chain(db, users):
    request = submit(db, users, amount=2000.0)
    approve_chain(db, request, users["manager"])
    engine.decide(db, request.id, users["finance1"], "changes_requested", comment="Split the invoice")
    db.commit()
    assert request.status == "changes_requested"

    engine.resubmit_request(db, request.id, users["sarah"], RequestResubmit(amount=800.0))
    db.commit()
    assert request.status == "pending"
    statuses = {s.name: s.status for s in request.steps}
    # Routing restarts from step 1: the earlier manager approval is discarded
    assert statuses["Manager approval"] == "active"
    assert statuses["Finance review"] == "pending"


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
    _delegate(db, users["manager"], users["vp"])
    engine.decide(db, request.id, users["vp"], "approved", comment="Approved while Mark is away")
    db.commit()
    decision = request.decisions[0]
    assert decision.acting_user_id == users["vp"].id
    assert decision.approver_id == users["manager"].id
    assert next(s for s in request.steps if s.name == "Finance review").status == "active"


def test_delegated_items_appear_in_inbox(db, users):
    request = submit(db, users, amount=500.0)
    _delegate(db, users["manager"], users["vp"])
    items = engine.inbox_for(db, users["vp"])
    delegated = [i for i in items if i["on_behalf_of"] is not None]
    assert len(delegated) == 1
    assert delegated[0]["request"].id == request.id
    assert delegated[0]["on_behalf_of"].id == users["manager"].id


def test_expired_delegation_grants_nothing(db, users):
    request = submit(db, users, amount=500.0)
    now = utcnow()
    db.add(
        Delegation(
            delegator_id=users["manager"].id, delegate_id=users["vp"].id,
            starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1),
        )
    )
    db.commit()
    with pytest.raises(PermissionDeniedError):
        engine.decide(db, request.id, users["vp"], "approved")


def test_requester_cannot_decide_own_request_even_via_delegation(db, users):
    """Closes the self-approval loophole: even if the requester holds delegated
    authority for the active step, they cannot decide on their own request."""
    request = submit(db, users, requester_key="manager2", amount=500.0)
    active = next(s for s in request.steps if s.status == "active")
    assert active.name == "Finance review"
    # Give the requester delegated authority for the active step (raw row simulates
    # any state, since the service-level matrix wouldn't allow finance -> manager)
    now = utcnow()
    db.add(
        Delegation(
            delegator_id=users["finance1"].id, delegate_id=users["manager2"].id,
            starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=4),
        )
    )
    db.commit()
    with pytest.raises(PermissionDeniedError, match="own request"):
        engine.decide(db, request.id, users["manager2"], "approved")


# --- Delegation role matrix (service layer) ------------------------------------------

def _delegation_payload(delegate):
    now = datetime.now(timezone.utc)
    return DelegationCreate(
        delegate_id=delegate.id, starts_at=now, ends_at=now + timedelta(days=7)
    )


@pytest.mark.parametrize(
    "delegator_key,delegate_key,ok",
    [
        ("manager", "manager2", True),
        ("manager", "finance1", True),
        ("manager", "vp", True),
        ("manager", "mike", False),      # manager -> employee forbidden
        ("finance1", "finance2", True),
        ("finance1", "vp", True),
        ("finance1", "manager", False),  # finance -> manager forbidden
        ("vp", "finance1", True),
        ("vp", "manager", False),        # vp -> manager forbidden
        ("vp", "mike", False),
    ],
)
def test_delegation_role_matrix(db, users, delegator_key, delegate_key, ok):
    if ok:
        delegation = create_delegation(db, users[delegator_key], _delegation_payload(users[delegate_key]))
        assert delegation.delegate_id == users[delegate_key].id
    else:
        with pytest.raises(ValidationFailedError):
            create_delegation(db, users[delegator_key], _delegation_payload(users[delegate_key]))


@pytest.mark.parametrize("delegator_key", ["sarah", "admin"])
def test_employee_and_admin_cannot_delegate(db, users, delegator_key):
    with pytest.raises(PermissionDeniedError):
        create_delegation(db, users[delegator_key], _delegation_payload(users["vp"]))


# --- Status feed ----------------------------------------------------------------------

def test_status_feed_messages(db, users):
    request = submit(db, users, amount=900.0)
    feed = engine.status_feed(db, users["sarah"])
    assert feed[0]["message"] == "Waiting for manager approval"

    engine.decide(db, request.id, users["manager"], "approved")
    db.commit()
    feed = engine.status_feed(db, users["sarah"])
    assert feed[0]["message"] == "approved by Mark Manager; waiting for finance approval"

    engine.decide(db, request.id, users["finance1"], "rejected", comment="no")
    db.commit()
    feed = engine.status_feed(db, users["sarah"])
    assert feed[0]["message"] == "rejected by Fiona Finance"


def test_status_feed_only_own_requests(db, users):
    submit(db, users, amount=100.0)
    assert engine.status_feed(db, users["mike"]) == []


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

    engine.decide(db, request.id, users["vp"], "approved")
    db.commit()
    assert step.status == "approved"
    assert request.status == "approved"


def test_sweep_ignores_steps_within_sla(db, users):
    request = submit(db, users, amount=500.0)
    assert engine.run_escalation_sweep(db) == 0
    step = next(s for s in request.steps if s.status == "active")
    assert step.escalated is False
