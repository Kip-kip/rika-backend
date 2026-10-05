# Rika app messages — customer ↔ Rika thread (T-B4-05)
import frappe
from frappe.utils import now
from .auth import _require_user


def _customer_projects(user):
    """Resolve the logged-in user's Rika Project docs (same chain as payments)."""
    cust = frappe.db.get_value("Rika Customer", {"user": user}, ["name", "phone"], as_dict=True)
    if not cust:
        return []
    docs = []
    phone = cust.phone
    lead = frappe.db.get_value("Rika Lead", {"phone": phone}, "name") if phone else None
    if lead:
        for row in frappe.db.get_all("Rika Project", {"customer": lead}, order_by="creation desc"):
            docs.append(frappe.get_doc("Rika Project", row.name))
    if not docs and phone:
        for row in frappe.db.get_all("Rika Project", order_by="creation desc"):
            doc = frappe.get_doc("Rika Project", row.name)
            if (doc.location or "").strip() and phone in doc.location:
                docs.append(doc)
    return docs


def _project_payload(doc):
    cust = frappe.db.get_value("Rika Customer", {"user": frappe.session.user}, "first_name")
    return {
        "name": doc.name,
        "project_name": doc.project_name or doc.name,
        "location": doc.location,
        "stage": doc.stage,
        "warranty_expires": str(doc.warranty_expires) if doc.warranty_expires else None,
        "warranty_start": str(doc.date_handover) if doc.date_handover else None,
    }


@frappe.whitelist(allow_guest=True)
def my_warranty():
    """GET /rika/api/warranty — logged-in customer's warranty status."""
    user = _require_user()
    docs = _customer_projects(user)
    if not docs:
        return {"ok": True, "warranty": None}
    doc = docs[0]
    p = _project_payload(doc)
    p["status"] = "active" if p["warranty_expires"] and str(p["warranty_expires"]) >= str(now()[:10]) else ("expired" if p["warranty_expires"] else "pending")
    return {"ok": True, "warranty": p}


@frappe.whitelist(allow_guest=True)
def list_messages():
    """GET /rika/api/messages — logged-in customer's message thread (their projects)."""
    user = _require_user()
    projects = [d.name for d in _customer_projects(user)]
    if not projects:
        return {"ok": True, "messages": []}
    rows = frappe.get_all(
        "Rika Message",
        filters={"project": ("in", projects)},
        fields=["name", "project", "sender", "message", "read_by_rika", "creation", "modified"],
        order_by="creation asc",
    )
    out = [
        {
            "id": r.name,
            "project": r.project,
            "sender": r.sender,
            "text": r.message,
            "read_by_rika": bool(r.read_by_rika),
            "at": r.creation,
        }
        for r in rows
    ]
    return {"ok": True, "messages": out}


@frappe.whitelist(allow_guest=True)
def post_message():
    """POST /rika/api/messages — customer posts a message to their thread."""
    user = _require_user()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    text = (d.get("message") or "").strip()
    if not text:
        frappe.throw("Message is empty.", frappe.ValidationError)
    if len(text) > 2000:
        frappe.throw("Message too long (max 2000 chars).", frappe.ValidationError)

    docs = _customer_projects(user)
    doc = None
    for cand in docs:
        if not project or cand.name == project:
            doc = cand
            break
    if not doc:
        frappe.throw("Project not found for this account.", frappe.ValidationError)

    cust = frappe.db.get_value("Rika Customer", {"user": user}, ["name", "phone", "first_name"], as_dict=True)
    m = frappe.new_doc("Rika Message")
    m.project = doc.name
    m.customer_name = (cust.first_name or "") if cust else ""
    m.phone = cust.phone if cust else None
    m.sender = "Customer"
    m.message = text
    m.insert(ignore_permissions=True)
    return {"ok": True, "id": m.name, "at": str(m.creation)}


@frappe.whitelist(allow_guest=True)
def reply_message():
    """POST /rika/api/messages/reply — Rika (admin) replies in the thread. X-Rika-Admin-Token required."""
    import os
    expected = os.environ.get("RIKA_ADMIN_TOKEN", "").strip()
    if not expected:
        frappe.throw("Admin API not configured (RIKA_ADMIN_TOKEN missing).", frappe.AuthenticationError)
    provided = (frappe.request.headers.get("X-Rika-Admin-Token") or "").strip()
    if provided != expected:
        frappe.throw("Invalid admin token.", frappe.AuthenticationError)
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    text = (d.get("message") or "").strip()
    if not text or not project:
        frappe.throw("project and message are required.", frappe.ValidationError)
    if not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    m = frappe.new_doc("Rika Message")
    m.project = project
    m.sender = "Rika"
    m.message = text
    m.insert(ignore_permissions=True)
    return {"ok": True, "id": m.name, "at": str(m.creation)}
