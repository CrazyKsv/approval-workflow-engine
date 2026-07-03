#!/usr/bin/env python3
"""End-to-end scenarios against the full running stack (frontend nginx -> backend -> db).

Requires a FRESH stack (autotest/e2e/run_e2e.sh rebuilds it with an empty database).
Talks to the API through the nginx proxy the way the SPA does. Stdlib only.

Scenarios:
  E2E-1  employee request walks manager -> finance -> vp chain to approved
  E2E-2  manager request skips the manager step
  E2E-3  status feed messages ("approved by X; waiting for Y approval")
  E2E-4  delegation matrix enforced; delegated decision records actor + authority
  E2E-5  self-approval blocked (requester with delegated authority)
  E2E-6  admin RBAC: no requests/delegations, but template management works
  E2E-7  employee/admin cannot delegate
  E2E-8  agent smoke (optional, real model): status question via /agent/chat [--with-agent]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:3000/api"
PASSWORD = "password123"
RESULTS: list[tuple[str, str]] = []


def call(method: str, path: str, token: str | None = None, body: dict | None = None, timeout: int = 120):
    request = urllib.request.Request(BASE + path, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(request, data=data, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def login(email: str) -> str:
    status, body = call("POST", "/auth/login", body={"email": email, "password": PASSWORD})
    assert status == 200, f"login failed for {email}: {status} {body}"
    return body["access_token"]


def check(name: str, condition: bool, detail: str = ""):
    RESULTS.append((name, "PASS" if condition else f"FAIL {detail}"))
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def main(with_agent: bool) -> int:
    tokens = {
        name: login(f"{name}@acme.com")
        for name in ("admin", "manager", "finance1", "vp", "sarah", "mike")
    }

    # E2E-1: employee chain
    status, body = call(
        "POST", "/requests", tokens["sarah"],
        {"template_id": 1, "title": "E2E-1 chain", "amount": 321, "data": {"expense_category": "e2e"}},
    )
    check("E2E-1 submit", status == 201, f"{status} {body}")
    request_id = body["id"]
    for approver in ("manager", "finance1", "vp"):
        status, inbox = call("GET", "/inbox", tokens[approver])
        check(f"E2E-1 {approver} inbox", any(i["request"]["id"] == request_id for i in inbox["items"]))
        status, body = call(
            "POST", f"/requests/{request_id}/decision", tokens[approver], {"decision": "approved"}
        )
        check(f"E2E-1 {approver} approve", status == 200, f"{status}")
    check("E2E-1 final approved", body["status"] == "approved", body["status"])

    # E2E-2: manager request skips manager step
    status, body = call(
        "POST", "/requests", tokens["manager"],
        {"template_id": 1, "title": "E2E-2 manager req", "amount": 55, "data": {"expense_category": "e2e"}},
    )
    statuses = {s["name"]: s["status"] for s in body["steps"]}
    check("E2E-2 manager step skipped", statuses.get("Manager approval") == "skipped", str(statuses))
    check("E2E-2 finance active", statuses.get("Finance review") == "active", str(statuses))

    # E2E-3: status feed
    status, body = call(
        "POST", "/requests", tokens["mike"],
        {"template_id": 1, "title": "E2E-3 feed", "amount": 77, "data": {"expense_category": "e2e"}},
    )
    feed_request_id = body["id"]
    call("POST", f"/requests/{feed_request_id}/decision", tokens["manager"], {"decision": "approved"})
    status, feed = call("GET", "/inbox/status", tokens["mike"])
    entry = next(i for i in feed if i["request"]["id"] == feed_request_id)
    check(
        "E2E-3 status message",
        entry["message"] == "approved by Mark Manager; waiting for finance approval",
        entry["message"],
    )

    # E2E-4: delegation matrix + delegated decision provenance
    status, _ = call(
        "POST", "/delegations", tokens["manager"],
        {"delegate_id": 7, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
    )
    check("E2E-4 manager->employee rejected", status == 422, str(status))
    status, delegation = call(
        "POST", "/delegations", tokens["manager"],
        {"delegate_id": 5, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
    )
    check("E2E-4 manager->vp accepted", status == 201, str(status))
    status, body = call(
        "POST", "/requests", tokens["sarah"],
        {"template_id": 2, "title": "E2E-4 delegated", "amount": 500, "data": {"vendor": "ACME"}},
    )
    delegated_request = body["id"]
    status, body = call(
        "POST", f"/requests/{delegated_request}/decision", tokens["vp"], {"decision": "approved"}
    )
    decision = body["decisions"][0]
    check(
        "E2E-4 provenance",
        decision["approver"]["email"] == "manager@acme.com" and decision["acting_user"]["email"] == "vp@acme.com",
        json.dumps(decision)[:120],
    )

    # E2E-5: self-approval blocked — sarah gets (raw) authority path is impossible via
    # API, so verify the closest reachable case: requester tries to decide own request.
    status, body = call(
        "POST", f"/requests/{delegated_request}/decision", tokens["sarah"], {"decision": "approved"}
    )
    check("E2E-5 self-decision blocked", status == 403, f"{status} {body}")
    call("DELETE", f"/delegations/{delegation['id']}", tokens["manager"])

    # E2E-6: admin RBAC
    status, _ = call(
        "POST", "/requests", tokens["admin"],
        {"template_id": 1, "title": "nope", "amount": 1, "data": {"expense_category": "x"}},
    )
    check("E2E-6 admin cannot submit", status == 403, str(status))
    status, _ = call(
        "POST", "/delegations", tokens["admin"],
        {"delegate_id": 5, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
    )
    check("E2E-6 admin cannot delegate", status == 403, str(status))
    status, template = call(
        "POST", "/templates", tokens["admin"],
        {
            "name": "E2E Contract Review",
            "fields": [{"name": "contract_value", "label": "Value", "type": "number", "required": True}],
            "steps": [
                {"step_order": 1, "name": "Manager", "approver_type": "role", "approver_role": "manager"},
                {"step_order": 2, "name": "VP", "approver_type": "role", "approver_role": "vp",
                 "condition": {"field": "contract_value", "op": ">=", "value": 50000}},
            ],
        },
    )
    check("E2E-6 admin creates template", status == 201, str(status))

    # E2E-7: employee cannot delegate
    status, _ = call(
        "POST", "/delegations", tokens["sarah"],
        {"delegate_id": 5, "starts_at": "2026-01-01T00:00:00Z", "ends_at": "2030-01-01T00:00:00Z"},
    )
    check("E2E-7 employee cannot delegate", status == 403, str(status))

    # E2E-8: agent smoke against the real model (optional)
    if with_agent:
        status, body = call(
            "POST", "/agent/chat", tokens["mike"],
            {"message": "What is the status of my requests?"}, timeout=150,
        )
        check("E2E-8 agent replies", status == 200 and bool(body["reply"]), str(status))
        tools_used = {e["tool_name"] for e in body["tool_events"]}
        check("E2E-8 agent used status tool", "get_request_status" in tools_used or "get_my_requests" in tools_used,
              str(tools_used))

    print("\n=== E2E RESULTS ===")
    for name, outcome in RESULTS:
        print(f"{outcome:6} {name}")
    print(f"\n{len(RESULTS)} checks, all passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(with_agent="--with-agent" in sys.argv))
    except AssertionError as exc:
        print("\n=== E2E RESULTS (with failure) ===")
        for name, outcome in RESULTS:
            print(f"{outcome:6} {name}")
        print(f"\nFAILED: {exc}")
        sys.exit(1)
