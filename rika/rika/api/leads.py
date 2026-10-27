# Rika CRM / lead management API (T-B5-09)
# Source tracking + funnel report (leads → customers → revenue per source).
import frappe
from .projects import _require_admin


SOURCES = ["Website", "Calculator", "WhatsApp", "Phone", "Referral", "Buying Guide", "Find Your Window"]
STATUSES = ["New", "Contacted", "Quoted", "Won", "Lost", "No Response"]


def _lead_customer_name(lead_name):
    """If this lead became a customer, return the customer's user name."""
    try:
        cust = frappe.db.get_value("Rika Customer", {"phone": frappe.db.get_value("Rika Lead", lead_name, "phone")}, "user")
        return cust or None
    except Exception:
        return None


def _lead_payload(doc):
    return {
        "name": doc.name,
        "first_name": doc.first_name,
        "last_name": doc.last_name,
        "phone": doc.phone,
        "email": doc.email,
        "location": doc.location,
        "window_type": doc.window_type,
        "quantity": doc.quantity,
        "source": doc.source,
        "status": doc.status,
        "lead_value": doc.lead_value,
        "notes": doc.notes,
        "created": str(doc.creation),
    }


@frappe.whitelist(allow_guest=True)
def list_leads():
    """GET /rika/api/leads — all leads, newest first (installer/admin token)."""
    _require_admin()
    rows = frappe.get_all("Rika Lead", fields=["name"], order_by="creation desc")
    out = []
    for r in rows:
        try:
            doc = frappe.get_doc("Rika Lead", r.name)
            out.append(_lead_payload(doc))
        except frappe.DoesNotExistError:
            continue
    return {"ok": True, "leads": out}


@frappe.whitelist(allow_guest=True)
def update_lead():
    """POST /rika/api/leads/update — update status/source/value (installer/admin token)."""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("lead") or "").strip()
    if not name or not frappe.db.exists("Rika Lead", name):
        frappe.throw("Lead not found.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Lead", name)
    if "status" in d and (d.get("status") or "").strip():
        status = (d.get("status") or "").strip()
        if status not in STATUSES:
            frappe.throw("Invalid status.", frappe.ValidationError)
        doc.status = status
    if "source" in d and (d.get("source") or "").strip():
        source = (d.get("source") or "").strip()
        if source not in SOURCES:
            frappe.throw("Invalid source.", frappe.ValidationError)
        doc.source = source
    if "lead_value" in d:
        doc.lead_value = float(d.get("lead_value") or 0)
    doc.db_update()
    return {"ok": True, "lead": _lead_payload(doc), "customer": _lead_customer_name(name)}


@frappe.whitelist(allow_guest=True)
def funnel():
    """GET /rika/api/leads/funnel — per-source funnel: leads → contacted → quoted → won → revenue."""
    _require_admin()
    leads = frappe.get_all("Rika Lead", fields=["name", "source", "status", "lead_value"])
    by_source = {}
    for s in SOURCES:
        by_source[s] = {"leads": 0, "contacted": 0, "quoted": 0, "won": 0, "lost": 0, "revenue": 0}
    for r in leads:
        s = r.source or "Website"
        if s not in by_source:
            by_source[s] = {"leads": 0, "contacted": 0, "quoted": 0, "won": 0, "lost": 0, "revenue": 0}
        by_source[s]["leads"] += 1
        if r.status in ("Contacted", "Quoted", "Won"):
            by_source[s]["contacted"] += 1
        if r.status in ("Quoted", "Won"):
            by_source[s]["quoted"] += 1
        if r.status == "Won":
            by_source[s]["won"] += 1
            by_source[s]["revenue"] += float(r.lead_value or 0)
        if r.status == "Lost":
            by_source[s]["lost"] += 1
    # drop empty sources
    out = {k: v for k, v in by_source.items() if v["leads"] > 0}
    total = {"leads": 0, "contacted": 0, "quoted": 0, "won": 0, "lost": 0, "revenue": 0}
    for v in out.values():
        for k in total:
            total[k] += v[k]
    return {"ok": True, "funnel": out, "total": total}


@frappe.whitelist(allow_guest=True)
def create_lead():
    """POST /rika/api/create-lead — guest lead capture (name/phone/email/source/notes)."""
    d = frappe.form_dict
    first_name = (d.get("first_name") or d.get("name") or "").strip()
    last_name = (d.get("last_name") or "").strip()
    phone = (d.get("phone") or "").strip()
    if not first_name:
        frappe.throw("Name is required.", frappe.ValidationError)
    if not phone:
        frappe.throw("Phone number is required.", frappe.ValidationError)
    source = (d.get("source") or "Website").strip()
    if source not in SOURCES:
        source = "Website"
    # dedupe: same phone → update, not duplicate
    existing = frappe.db.get_value("Rika Lead", {"phone": phone}, "name")
    if existing:
        doc = frappe.get_doc("Rika Lead", existing)
        doc.last_name = last_name or doc.last_name
        if d.get("email"):
            doc.email = (d.get("email") or "").strip()
        if d.get("notes"):
            doc.notes = (d.get("notes") or "").strip()
        doc.source = source
        doc.db_update()
        return {"ok": True, "ref": doc.name, "updated": True}
    doc = frappe.new_doc("Rika Lead")
    doc.first_name = first_name
    doc.last_name = last_name
    doc.phone = phone
    if d.get("email"):
        doc.email = (d.get("email") or "").strip()
    doc.source = source
    if d.get("notes"):
        doc.notes = (d.get("notes") or "").strip()
    doc.status = "New"
    doc.insert(ignore_permissions=True)
    doc.db_set("status", "New", commit=False)
    return {"ok": True, "ref": doc.name}
