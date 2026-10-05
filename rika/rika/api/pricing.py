# Rika pricing intelligence API (T-B5-03)
# Per-project cost breakdown, gross profit, margin. Admin-only.
import frappe
from .projects import _require_admin

COST_FIELDS = [
    "cost_aluminium", "cost_glass", "cost_hardware", "cost_fabrication",
    "cost_installation", "cost_transport", "cost_wastage", "cost_marketing",
]


def _cost_payload(doc):
    return {
        "name": doc.name,
        "project": doc.project,
        "selling_price": doc.selling_price,
        "costs": {f: getattr(doc, f) or 0 for f in COST_FIELDS},
        "total_cost": doc.total_cost,
        "gross_profit": doc.gross_profit,
        "margin_pct": doc.margin_pct,
        "notes": doc.notes,
        "created": str(doc.creation),
    }


@frappe.whitelist(allow_guest=True)
def list_costs():
    """GET /rika/api/pricing — all project cost records + project names (admin)."""
    _require_admin()
    rows = frappe.get_all("Rika Project Cost", fields=["name"], order_by="creation desc")
    out = []
    for r in rows:
        doc = frappe.get_doc("Rika Project Cost", r.name)
        item = _cost_payload(doc)
        try:
            proj = frappe.get_doc("Rika Project", doc.project)
            item["project_name"] = proj.project_name
            item["stage"] = proj.stage
        except frappe.DoesNotExistError:
            item["project_name"] = doc.project
            item["stage"] = None
        out.append(item)
    return {"ok": True, "costs": out}


@frappe.whitelist(allow_guest=True)
def save_cost():
    """POST /rika/api/pricing — create or update a cost record for a project (admin)."""
    _require_admin()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    selling = float(d.get("selling_price") or 0)
    if selling <= 0:
        frappe.throw("Selling price must be greater than zero.", frappe.ValidationError)
    existing = frappe.db.get_value("Rika Project Cost", {"project": project}, "name")
    if existing:
        doc = frappe.get_doc("Rika Project Cost", existing)
    else:
        doc = frappe.new_doc("Rika Project Cost")
        doc.project = project
    doc.selling_price = selling
    for f in COST_FIELDS:
        doc.set(f, float(d.get(f) or 0))
    doc.notes = (d.get("notes") or "").strip()
    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)
    return {"ok": True, "cost": _cost_payload(doc)}
