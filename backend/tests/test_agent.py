"""Agent tests with a scripted fake LLM: multi-turn submission with confirmation gate,
tool authorization, and trace persistence."""
import json
from types import SimpleNamespace

from sqlalchemy import select

from app.agent import orchestrator
from app.agent.tools import run_tool
from app.models import AgentMessage, ApprovalRequest, AuditLog
from tests.conftest import auth_headers


def assistant_text(content):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def assistant_tool_call(name, args, call_id="call_1", content=None):
    tool_call = SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )
    message = SimpleNamespace(content=content, tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Returns scripted responses in order and records every request payload."""

    def __init__(self, responses):
        self.calls = []
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return responses.pop(0)

        self.chat = SimpleNamespace(completions=Completions())


def install_fake(monkeypatch, responses) -> FakeClient:
    fake = FakeClient(responses)
    monkeypatch.setattr(orchestrator, "get_client", lambda: fake)
    return fake


def test_multi_turn_submission_with_confirmation_gate(client, users, monkeypatch, db):
    template_id = users["purchase_template"].id
    submit_args = {
        "template_id": template_id,
        "title": "Laptop purchase",
        "amount": 5000,
        "data": {"vendor": "Apple"},
    }
    fake = install_fake(
        monkeypatch,
        [
            # Turn 1: model inspects templates, tries to submit, hits the confirmation gate
            assistant_tool_call("list_workflow_templates", {}, call_id="c1"),
            assistant_tool_call("submit_request", submit_args, call_id="c2"),
            assistant_text("I'd like to submit a $5,000 laptop Purchase Order. Shall I proceed?"),
            # Turn 2: user confirmed; model submits with confirmed=true and reports back
            assistant_tool_call("submit_request", {**submit_args, "confirmed": True}, call_id="c3"),
            assistant_text("Done! Request submitted and awaiting Manager approval."),
        ],
    )

    headers = auth_headers(users["sarah"])
    resp = client.post(
        "/api/agent/chat",
        json={"message": "I need approval for a $5,000 laptop purchase from Apple."},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Shall I proceed" in body["reply"]
    # No request was created yet — the confirmation gate blocked execution server-side
    assert db.scalar(select(ApprovalRequest)) is None
    gate = next(e for e in body["tool_events"] if e["tool_name"] == "submit_request")
    assert gate["result"]["status"] == "confirmation_required"

    resp = client.post(
        "/api/agent/chat",
        json={"message": "Yes, please submit it.", "conversation_id": body["conversation_id"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == body["conversation_id"]

    request = db.scalar(select(ApprovalRequest))
    assert request is not None
    assert request.requester_id == users["sarah"].id
    assert float(request.amount) == 5000.0
    assert request.status == "pending"
    # $5,000 is not > $5,000: finance is skipped, manager step is active
    assert {s.name: s.status for s in request.steps}["Manager approval"] == "active"

    # The whole turn history (including turn-1 messages) was replayed to the model
    final_call_messages = fake.calls[-1]["messages"]
    roles = [m["role"] for m in final_call_messages]
    assert roles[0] == "system"
    assert roles.count("user") == 2

    # Agent action shows up in the audit trail under the real user
    audit_actions = {a.action for a in db.scalars(select(AuditLog)).all()}
    assert "request_submitted" in audit_actions

    # Full trace persisted for observability
    trace = client.get(f"/api/agent/conversations/{body['conversation_id']}", headers=headers).json()
    tool_rows = [m for m in trace["messages"] if m["role"] == "tool"]
    assert {t["tool_name"] for t in tool_rows} == {"list_workflow_templates", "submit_request"}
    assert all(t["latency_ms"] is not None for t in tool_rows)


def test_agent_pending_approvals_includes_delegations(client, users, monkeypatch, db):
    # Sarah submits; manager delegates to vp (allowed by the matrix); vp asks the assistant
    client.post(
        "/api/requests",
        json={
            "template_id": users["expense_template"].id,
            "title": "Team offsite",
            "amount": 700,
            "data": {"expense_category": "events"},
        },
        headers=auth_headers(users["sarah"]),
    )
    resp = client.post(
        "/api/delegations",
        json={"delegate_id": users["vp"].id, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        headers=auth_headers(users["manager"]),
    )
    assert resp.status_code == 201
    install_fake(
        monkeypatch,
        [
            assistant_tool_call("get_pending_approvals", {}),
            assistant_text("You have 1 pending approval, delegated from Mark Manager."),
        ],
    )
    resp = client.post(
        "/api/agent/chat",
        json={"message": "What requests are waiting for my approval?"},
        headers=auth_headers(users["vp"]),
    )
    event = resp.json()["tool_events"][0]
    approvals = event["result"]["pending_approvals"]
    delegated = [a for a in approvals if a["on_behalf_of"]]
    assert len(delegated) == 1
    assert delegated[0]["on_behalf_of"]["name"] == "Mark Manager"


def test_agent_status_feed_tool_formats_messages(client, users, monkeypatch, db):
    client.post(
        "/api/requests",
        json={
            "template_id": users["expense_template"].id,
            "title": "Team offsite",
            "amount": 700,
            "data": {"expense_category": "events"},
        },
        headers=auth_headers(users["sarah"]),
    )
    install_fake(
        monkeypatch,
        [
            assistant_tool_call("get_request_status", {}),
            assistant_text("Your request is waiting for manager approval."),
        ],
    )
    resp = client.post(
        "/api/agent/chat",
        json={"message": "What's the status of my requests?"},
        headers=auth_headers(users["sarah"]),
    )
    event = resp.json()["tool_events"][0]
    items = event["result"]["request_status"]
    assert len(items) == 1
    assert "waiting for manager approval" in items[0]["message"].lower()


def test_agent_delegation_tool_enforces_role_matrix(db, users):
    # An employee cannot delegate at all — tool relays the structured error
    result = run_tool(
        db, users["sarah"], "create_delegation",
        {
            "delegate_id": users["vp"].id,
            "starts_at": "2026-01-01T00:00:00",
            "ends_at": "2030-01-01T00:00:00",
            "confirmed": True,
        },
    )
    assert result["error"] == "PermissionDeniedError"
    # vp -> manager is outside the matrix
    result = run_tool(
        db, users["vp"], "create_delegation",
        {
            "delegate_id": users["manager"].id,
            "starts_at": "2026-01-01T00:00:00",
            "ends_at": "2030-01-01T00:00:00",
            "confirmed": True,
        },
    )
    assert result["error"] == "ValidationFailedError"


def test_agent_admin_cannot_submit_requests(db, users):
    result = run_tool(
        db, users["admin"], "submit_request",
        {
            "template_id": users["expense_template"].id,
            "title": "Admin sneaky request",
            "amount": 10,
            "data": {"expense_category": "misc"},
            "confirmed": True,
        },
    )
    assert result["error"] == "PermissionDeniedError"


def test_tool_layer_enforces_authorization(db, users):
    # An employee must not be able to create templates through the agent tools
    result = run_tool(
        db, users["sarah"], "create_workflow_template",
        {
            "name": "Sneaky",
            "steps": [{"step_order": 1, "name": "Me", "approver_type": "role", "approver_role": "employee"}],
            "confirmed": True,
        },
    )
    assert result["error"] == "PermissionDeniedError"


def test_tool_rejects_decision_by_non_approver(db, users):
    from app.schemas import RequestCreate
    from app.services import engine as workflow_engine

    request = workflow_engine.submit_request(
        db, users["sarah"],
        RequestCreate(
            template_id=users["expense_template"].id, title="Chair", amount=200.0,
            data={"expense_category": "furniture"},
        ),
    )
    db.commit()
    result = run_tool(
        db, users["mike"], "decide_request",
        {"request_id": request.id, "decision": "approved", "confirmed": True},
    )
    assert result["error"] == "PermissionDeniedError"


def test_model_failure_returns_graceful_error(client, users, monkeypatch, db):
    class ExplodingClient:
        def __init__(self):
            def boom(**kwargs):
                raise RuntimeError("network down")

            self.chat = SimpleNamespace(completions=SimpleNamespace(create=boom))

    monkeypatch.setattr(orchestrator, "get_client", lambda: ExplodingClient())
    resp = client.post(
        "/api/agent/chat", json={"message": "hello"}, headers=auth_headers(users["sarah"])
    )
    assert resp.status_code == 200
    assert "unavailable" in resp.json()["reply"]
    # The failure is persisted in the trace
    row = db.scalar(select(AgentMessage).where(AgentMessage.error.is_not(None)))
    assert row is not None
