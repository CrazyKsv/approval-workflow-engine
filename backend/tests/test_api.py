"""API tests: auth, RBAC, request lifecycle over HTTP, pagination, audit."""
from tests.conftest import auth_headers


def test_login_and_me(client, users):
    resp = client.post("/api/auth/login", json={"email": "sarah@acme.com", "password": "password123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "sarah@acme.com"


def test_login_rejects_bad_password(client, users):
    resp = client.post("/api/auth/login", json={"email": "sarah@acme.com", "password": "wrong"})
    assert resp.status_code == 401


def test_endpoints_require_auth(client, users):
    assert client.get("/api/inbox").status_code == 401
    assert client.get("/api/requests").status_code == 401
    assert client.post("/api/agent/chat", json={"message": "hi"}).status_code == 401


def test_template_creation_requires_admin(client, users):
    payload = {
        "name": "Ad-hoc",
        "steps": [{"step_order": 1, "name": "Manager", "approver_type": "role", "approver_role": "manager"}],
    }
    resp = client.post("/api/templates", json=payload, headers=auth_headers(users["sarah"]))
    assert resp.status_code == 403
    resp = client.post("/api/templates", json=payload, headers=auth_headers(users["admin"]))
    assert resp.status_code == 201
    assert resp.json()["steps"][0]["approver_role"] == "manager"


def test_template_rejects_bad_condition_field(client, users):
    payload = {
        "name": "Broken",
        "steps": [
            {
                "step_order": 1, "name": "Manager", "approver_type": "role", "approver_role": "manager",
                "condition": {"field": "nonexistent", "op": ">", "value": 1},
            }
        ],
    }
    resp = client.post("/api/templates", json=payload, headers=auth_headers(users["admin"]))
    assert resp.status_code == 422


def test_full_request_lifecycle_over_http(client, users):
    sarah, manager, finance = users["sarah"], users["manager"], users["finance1"]

    resp = client.post(
        "/api/requests",
        json={
            "template_id": users["expense_template"].id,
            "title": "Conference travel",
            "amount": 2500,
            "data": {"expense_category": "travel"},
        },
        headers=auth_headers(sarah),
    )
    assert resp.status_code == 201
    request_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    inbox = client.get("/api/inbox", headers=auth_headers(manager)).json()
    assert inbox["total"] == 1
    assert inbox["items"][0]["request"]["id"] == request_id

    resp = client.post(
        f"/api/requests/{request_id}/decision",
        json={"decision": "approved", "comment": "ok"},
        headers=auth_headers(manager),
    )
    assert resp.status_code == 200

    inbox = client.get("/api/inbox", headers=auth_headers(finance)).json()
    assert inbox["total"] == 1
    resp = client.post(
        f"/api/requests/{request_id}/decision",
        json={"decision": "approved"},
        headers=auth_headers(finance),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    audit = client.get(f"/api/audit?request_id={request_id}", headers=auth_headers(sarah)).json()
    actions = {entry["action"] for entry in audit["items"]}
    assert {"request_submitted", "step_activated", "decision_approved", "request_approved"} <= actions


def test_non_approver_gets_403_on_decision(client, users):
    resp = client.post(
        "/api/requests",
        json={
            "template_id": users["expense_template"].id,
            "title": "Desk",
            "amount": 300,
            "data": {"expense_category": "furniture"},
        },
        headers=auth_headers(users["sarah"]),
    )
    request_id = resp.json()["id"]
    resp = client.post(
        f"/api/requests/{request_id}/decision",
        json={"decision": "approved"},
        headers=auth_headers(users["mike"]),
    )
    assert resp.status_code == 403


def test_request_visibility(client, users):
    resp = client.post(
        "/api/requests",
        json={
            "template_id": users["expense_template"].id,
            "title": "Books",
            "amount": 90,
            "data": {"expense_category": "education"},
        },
        headers=auth_headers(users["sarah"]),
    )
    request_id = resp.json()["id"]
    # Another employee can't see it; an approver and an admin can.
    assert client.get(f"/api/requests/{request_id}", headers=auth_headers(users["mike"])).status_code == 403
    assert client.get(f"/api/requests/{request_id}", headers=auth_headers(users["manager"])).status_code == 200
    assert client.get(f"/api/requests/{request_id}", headers=auth_headers(users["admin"])).status_code == 200


def test_missing_required_field_is_422(client, users):
    resp = client.post(
        "/api/requests",
        json={"template_id": users["expense_template"].id, "title": "No data", "amount": 10, "data": {}},
        headers=auth_headers(users["sarah"]),
    )
    assert resp.status_code == 422
    assert "expense_category" in resp.json()["detail"]


def test_pagination(client, users):
    for i in range(3):
        client.post(
            "/api/requests",
            json={
                "template_id": users["expense_template"].id,
                "title": f"Item {i}",
                "amount": 50,
                "data": {"expense_category": "misc"},
            },
            headers=auth_headers(users["sarah"]),
        )
    resp = client.get("/api/requests?page=1&size=2", headers=auth_headers(users["sarah"])).json()
    assert resp["total"] == 3
    assert len(resp["items"]) == 2
    resp = client.get("/api/requests?page=2&size=2", headers=auth_headers(users["sarah"])).json()
    assert len(resp["items"]) == 1


def test_delegation_endpoints(client, users):
    resp = client.post(
        "/api/delegations",
        json={
            "delegate_id": users["mike"].id,
            "starts_at": "2026-01-01T00:00:00Z",
            "ends_at": "2030-01-01T00:00:00Z",
            "reason": "Vacation",
        },
        headers=auth_headers(users["manager"]),
    )
    assert resp.status_code == 201
    delegation_id = resp.json()["id"]

    listed = client.get("/api/delegations", headers=auth_headers(users["mike"])).json()
    assert listed["total"] == 1

    resp = client.delete(f"/api/delegations/{delegation_id}", headers=auth_headers(users["sarah"]))
    assert resp.status_code == 403
    resp = client.delete(f"/api/delegations/{delegation_id}", headers=auth_headers(users["manager"]))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_global_audit_admin_only(client, users):
    assert client.get("/api/audit", headers=auth_headers(users["sarah"])).status_code == 403
    assert client.get("/api/audit", headers=auth_headers(users["admin"])).status_code == 200
