"""Tests for the declarative YAML workflow-template catalog loader."""
import textwrap

from sqlalchemy import func, select

from app.models import User, WorkflowTemplate
from app.services.template_loader import load_templates_from_yaml
from tests.conftest import PW_HASH


def _admin(db):
    admin = User(email="admin@acme.com", name="Alice Admin", role="admin", password_hash=PW_HASH)
    db.add(admin)
    db.commit()
    return admin


def _write(tmp_path, content, name="catalog.yaml"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(content))
    return str(path)


CATALOG_A = """
    templates:
      - name: Travel Reimbursement
        description: Business travel
        category: travel
        fields:
          - {name: amount, label: Amount, type: number, required: true}
          - {name: destination, label: Destination, type: string, required: true}
        steps:
          - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
          - {step_order: 2, name: Finance review, approver_type: role, approver_role: finance, approval_mode: any}
          - {step_order: 3, name: VP sign-off, approver_type: role, approver_role: vp}
      - name: Equipment Request
        category: it
        fields:
          - {name: amount, label: Amount, type: number, required: true}
        steps:
          - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
    """

CATALOG_B = """
    templates:
      - name: Travel Reimbursement
        description: Business travel
        category: travel
        fields:
          - {name: amount, label: Amount, type: number, required: true}
          - {name: destination, label: Destination, type: string, required: true}
        steps:
          - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
          - {step_order: 2, name: Finance review, approver_type: role, approver_role: finance, approval_mode: any}
          - {step_order: 3, name: VP sign-off, approver_type: role, approver_role: vp}
      - name: Equipment Request
        category: it
        fields:
          - {name: amount, label: Amount, type: number, required: true}
        steps:
          - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
      - name: Contractor Onboarding
        category: hr
        steps:
          - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
    """


def test_loads_all_templates_into_empty_db(db, tmp_path):
    _admin(db)
    result = load_templates_from_yaml(db, _write(tmp_path, CATALOG_A))
    assert result["created"] == 2
    assert result["errors"] == []
    names = set(db.scalars(select(WorkflowTemplate.name)).all())
    assert names == {"Travel Reimbursement", "Equipment Request"}
    travel = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == "Travel Reimbursement"))
    assert [s.approver_role for s in travel.steps] == ["manager", "finance", "vp"]
    assert travel.created_by_id is not None  # attributed to the admin
    assert {f["name"] for f in travel.fields} == {"amount", "destination"}


def test_load_is_idempotent(db, tmp_path):
    _admin(db)
    path = _write(tmp_path, CATALOG_A)
    load_templates_from_yaml(db, path)
    second = load_templates_from_yaml(db, path)
    assert second["created"] == 0
    assert second["skipped"] == 2
    assert db.scalar(select(func.count()).select_from(WorkflowTemplate)) == 2


def test_load_adds_only_new_templates(db, tmp_path):
    """Onboarding by PR: adding an entry to the catalog creates only the new template."""
    _admin(db)
    load_templates_from_yaml(db, _write(tmp_path, CATALOG_A))
    result = load_templates_from_yaml(db, _write(tmp_path, CATALOG_B, "catalog2.yaml"))
    assert result["created"] == 1
    assert result["created_names"] == ["Contractor Onboarding"]
    assert db.scalar(select(func.count()).select_from(WorkflowTemplate)) == 3


def test_admin_and_assistant_created_templates_are_not_touched(db, tmp_path):
    """A template that already exists by name (e.g. created via the UI/assistant) is skipped."""
    _admin(db)
    db.add(WorkflowTemplate(name="Travel Reimbursement", category="custom", fields=[]))
    db.commit()
    result = load_templates_from_yaml(db, _write(tmp_path, CATALOG_A))
    # Only the second catalog template is new; the pre-existing one is left as-is.
    assert result["created"] == 1
    assert result["created_names"] == ["Equipment Request"]
    kept = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == "Travel Reimbursement"))
    assert kept.category == "custom"  # untouched


def test_missing_file_is_graceful(db):
    result = load_templates_from_yaml(db, "/nonexistent/workflow_templates.yaml")
    assert result == {"created": 0, "skipped": 0, "errors": [], "created_names": []}


def test_malformed_entry_is_isolated(db, tmp_path):
    """A single invalid entry is logged and skipped; valid entries still load."""
    _admin(db)
    catalog = """
        templates:
          - name: Good One
            steps:
              - {step_order: 1, name: Manager approval, approver_type: role, approver_role: manager}
          - name: Bad One
            steps:
              - {step_order: 1, name: Bad step, approver_type: role, approver_role: wizard}
    """
    result = load_templates_from_yaml(db, _write(tmp_path, catalog))
    assert result["created"] == 1
    assert result["created_names"] == ["Good One"]
    assert len(result["errors"]) == 1
    assert result["errors"][0]["name"] == "Bad One"
    assert db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.name == "Bad One")) is None


def test_bundled_catalog_is_valid(db):
    """CI guard: the shipped app/workflow_templates.yaml loads cleanly (fail-fast on bad PRs)."""
    _admin(db)
    result = load_templates_from_yaml(db)  # default path = settings.templates_file
    assert result["errors"] == []
    assert result["created"] == 3
    names = set(db.scalars(select(WorkflowTemplate.name)).all())
    assert names == {"Expense Report", "Purchase Order", "Time Off Request"}
    for template in db.scalars(select(WorkflowTemplate)).all():
        assert [s.approver_role for s in template.steps] == ["manager", "finance", "vp"], template.name
