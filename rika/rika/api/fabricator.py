# Rika fabricator portal API (T-B5-01)
# Production orders: receive, status flow, list.
import frappe
from .projects import _require_admin

ORDER_STATUSES = ["Pending", "Accepted", "In Production", "Complete", "Collected"]
VALID_TRANSITIONS = {
    "Pending": ["Accepted"],
    "Accepted": ["In Production"],
    "In Production": ["Complete"],
    "Complete": ["Collected"],
    "Collected": [],
}


def _production_order_payload(doc):
    return {
        "name": doc.name,
        "project": doc.project,
        "order_no": doc.order_no or doc.name,
        "spec_summary": doc.spec_summary,
        "status": doc.status,
        "notes": doc.notes,
        "created": str(doc.creation),
    }


@frappe.whitelist(allow_guest=True)
def list_orders():
    """GET /rika/api/fabricator/orders — list production orders (admin)."""
    _require_admin()
    rows = frappe.get_all("Rika Production Order", fields=["name"], order_by="creation desc")
    docs = [frappe.get_doc("Rika Production Order", r.name) for r in rows]
    return {"ok": True, "orders": [_production_order_payload(d) for d in docs]}


@frappe.whitelist(allow_guest=True)
def create_order():
    """POST /rika/api/fabricator/orders — create a production order from a project (admin)."""
    _require_admin()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    existing = frappe.db.get_value("Rika Production Order", {"project": project}, "name")
    if existing:
        frappe.throw("A production order already exists for this project.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Project", project)
    p = frappe.new_doc("Rika Production Order")
    p.project = project
    p.spec_summary = (d.get("spec_summary") or "").strip()
    p.status = "Pending"
    p.notes = (d.get("notes") or "").strip()
    p.insert(ignore_permissions=True)
    return {"ok": True, "order": _production_order_payload(p)}


@frappe.whitelist(allow_guest=True)
def update_status():
    """POST /rika/api/fabricator/orders/status — advance order status (admin)."""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("order") or "").strip()
    new_status = (d.get("status") or "").strip()
    if not name or not frappe.db.exists("Rika Production Order", name):
        frappe.throw("Order not found.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Production Order", name)
    if new_status not in ORDER_STATUSES:
        frappe.throw("Invalid status.", frappe.ValidationError)
    allowed = VALID_TRANSITIONS.get(doc.status, [])
    if new_status != doc.status and new_status not in allowed:
        frappe.throw(f"Cannot move from {doc.status} to {new_status}.", frappe.ValidationError)
    doc.status = new_status
    doc.db_set("status", new_status)
    return {"ok": True, "order": _production_order_payload(doc)}


@frappe.whitelist(allow_guest=True)
def create_from_project():
    """POST /rika/api/fabricator/from-project — create production order + set project stage to Fabrication (admin)."""
    _require_admin()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    existing = frappe.db.get_value("Rika Production Order", {"project": project}, "name")
    if existing:
        frappe.throw("A production order already exists for this project.", frappe.ValidationError)
    pdoc = frappe.get_doc("Rika Project", project)
    if pdoc.stage not in ("Approval", "Fabrication"):
        frappe.throw(f"Project is in stage {pdoc.stage}; must be Approval or Fabrication to create a production order.", frappe.ValidationError)
    p = frappe.new_doc("Rika Production Order")
    p.project = project
    p.spec_summary = (d.get("spec_summary") or "").strip()
    p.status = "Pending"
    p.notes = (d.get("notes") or "").strip()
    p.insert(ignore_permissions=True)
    pdoc.db_set("stage", "Fabrication")
    return {"ok": True, "order": _production_order_payload(p), "stage": "Fabrication"}
