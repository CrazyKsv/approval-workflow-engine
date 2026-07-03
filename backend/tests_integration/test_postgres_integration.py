"""Integration suite: API + engine + ORM against real PostgreSQL, from an empty DB."""
from sqlalchemy import inspect

from app.db import engine
from tests_integration.conftest import auth


def test_migration_created_all_tables(migrated_db):
    tables = set(inspect(engine).get_table_names())
    expected = {
        "users", "groups", "user_groups", "workflow_templates", "template_steps",
        "approval_requests", "step_instances", "step_approvers", "decisions",
        "delegations", "audit_log", "agent_conversations", "agent_messages",
        "alembic_version",
    }
    assert expected <= tables


def test_seeded_templates_use_standard_chain(client, tokens):
    resp = client.get("/api/templates?size=10", headers=auth(tokens, "sarah"))
    assert resp.status_code == 200
    templates = resp.json()["items"]
    assert {t["name"] for t in templates} == {"Expense Report", "Purchase Order", "Time Off Request"}
    for template in templates:
        roles = [s["approver_role"] for s in template["steps"]]
        assert roles == ["manager", "finance", "vp"], template["name"]


def test_employee_chain_lifecycle_on_postgres(client, tokens):
    resp = client.post(
        "/api/requests",
        json={
            "template_id": 1,
            "title": "INT employee chain",
            "amount": 1234.56,
            "data": {"expense_category": "integration"},
        },
        headers=auth(tokens, "sarah"),
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]

    for approver in ("manager", "finance1", "vp"):
        inbox = client.get("/api/inbox", headers=auth(tokens, approver)).json()
        assert any(i["request"]["id"] == request_id for i in inbox["items"]), approver
        resp = client.post(
            f"/api/requests/{request_id}/decision",
            json={"decision": "approved"},
            headers=auth(tokens, approver),
        )
        assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    audit = client.get(f"/api/audit?request_id={request_id}&size=50", headers=auth(tokens, "sarah")).json()
    actions = [a["action"] for a in audit["items"]]
    assert actions.count("decision_approved") == 3
    assert "request_approved" in actions


def test_manager_request_skips_manager_step_on_postgres(client, tokens):
    resp = client.post(
        "/api/requests",
        json={
            "template_id": 1,
            "title": "INT manager request",
            "amount": 50,
            "data": {"expense_category": "integration"},
        },
        headers=auth(tokens, "manager"),
    )
    assert resp.status_code == 201
    body = resp.json()
    statuses = {s["name"]: s["status"] for s in body["steps"]}
    assert statuses["Manager approval"] == "skipped"
    assert statuses["Finance review"] == "active"


def test_status_feed_message_on_postgres(client, tokens):
    resp = client.post(
        "/api/requests",
        json={
            "template_id": 1,
            "title": "INT status feed",
            "amount": 10,
            "data": {"expense_category": "integration"},
        },
        headers=auth(tokens, "mike"),
    )
    request_id = resp.json()["id"]
    client.post(
        f"/api/requests/{request_id}/decision",
        json={"decision": "approved"},
        headers=auth(tokens, "manager"),
    )
    feed = client.get("/api/inbox/status", headers=auth(tokens, "mike")).json()
    entry = next(item for item in feed if item["request"]["id"] == request_id)
    assert entry["message"] == "approved by Mark Manager; waiting for finance approval"


def test_delegation_matrix_and_delegated_decision_on_postgres(client, tokens):
    # manager -> employee rejected; manager -> vp accepted
    bad = client.post(
        "/api/delegations",
        json={"delegate_id": 7, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        headers=auth(tokens, "manager"),
    )
    assert bad.status_code == 422
    good = client.post(
        "/api/delegations",
        json={"delegate_id": 5, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        headers=auth(tokens, "manager"),
    )
    assert good.status_code == 201
    delegation_id = good.json()["id"]

    resp = client.post(
        "/api/requests",
        json={
            "template_id": 2,
            "title": "INT delegated decision",
            "amount": 999,
            "data": {"vendor": "ACME", "expense_category": "x"},
        },
        headers=auth(tokens, "sarah"),
    )
    request_id = resp.json()["id"]
    # VP acts on the manager step via delegation
    resp = client.post(
        f"/api/requests/{request_id}/decision",
        json={"decision": "approved", "comment": "delegated"},
        headers=auth(tokens, "vp"),
    )
    assert resp.status_code == 200
    decisions = resp.json()["decisions"]
    assert decisions[0]["approver"]["email"] == "manager@acme.com"
    assert decisions[0]["acting_user"]["email"] == "vp@acme.com"

    client.delete(f"/api/delegations/{delegation_id}", headers=auth(tokens, "manager"))


def test_admin_rbac_on_postgres(client, tokens):
    resp = client.post(
        "/api/requests",
        json={"template_id": 1, "title": "admin blocked", "amount": 1, "data": {"expense_category": "x"}},
        headers=auth(tokens, "admin"),
    )
    assert resp.status_code == 403
    resp = client.post(
        "/api/delegations",
        json={"delegate_id": 5, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
        headers=auth(tokens, "admin"),
    )
    assert resp.status_code == 403
    # Admin can still manage templates
    resp = client.post(
        "/api/templates",
        json={
            "name": "INT custom conditional",
            "fields": [{"name": "amount", "label": "Amount", "type": "number", "required": True}],
            "steps": [
                {"step_order": 1, "name": "Manager", "approver_type": "role", "approver_role": "manager"},
                {
                    "step_order": 2, "name": "VP big spend", "approver_type": "role", "approver_role": "vp",
                    "condition": {"field": "amount", "op": ">=", "value": 10000},
                },
            ],
        },
        headers=auth(tokens, "admin"),
    )
    assert resp.status_code == 201


def test_jsonb_condition_routing_on_postgres(client, tokens):
    """Conditions stored as JSONB round-trip and route correctly on Postgres."""
    templates = client.get("/api/templates?size=20", headers=auth(tokens, "sarah")).json()["items"]
    custom = next(t for t in templates if t["name"] == "INT custom conditional")
    resp = client.post(
        "/api/requests",
        json={"template_id": custom["id"], "title": "INT big spend", "amount": 20000, "data": {}},
        headers=auth(tokens, "sarah"),
    )
    statuses = {s["name"]: s["status"] for s in resp.json()["steps"]}
    assert statuses == {"Manager": "active", "VP big spend": "pending"}

    resp = client.post(
        "/api/requests",
        json={"template_id": custom["id"], "title": "INT small spend", "amount": 50, "data": {}},
        headers=auth(tokens, "sarah"),
    )
    statuses = {s["name"]: s["status"] for s in resp.json()["steps"]}
    assert statuses == {"Manager": "active", "VP big spend": "skipped"}
