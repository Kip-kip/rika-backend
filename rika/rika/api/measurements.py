# Rika measurement recorder API (T-B5-08)
# Installer records every opening (W01, W02…) with dims, type, photos, notes.
# Flows into quote + production. Installer token = admin token (field staff).
import frappe
from .projects import _require_admin


def _opening_payload(row):
    return {
        "label": row.get("label"),
        "type": row.get("type"),
        "width": row.get("width"),
        "height": row.get("height"),
        "qty": row.get("qty") or 1,
        "finish": row.get("finish"),
        "glass": row.get("glass"),
        "photo": row.get("photo"),
        "notes": row.get("notes"),
    }


def _measurement_payload(doc):
    return {
        "name": doc.name,
        "customer_name": doc.customer_name,
        "phone": doc.phone,
        "address": doc.address,
        "measurer": doc.measurer,
        "date": str(doc.date) if doc.date else None,
        "notes": doc.notes,
        "openings": [_opening_payload(row.as_dict()) for row in doc.openings],
        "created": str(doc.creation),
    }


@frappe.whitelist(allow_guest=True)
def list_measurements():
    """GET /rika/api/measurements — all recordings, newest first (installer token)."""
    _require_admin()
    rows = frappe.get_all("Rika Measurement", fields=["name"], order_by="creation desc")
    out = []
    for r in rows:
        try:
            doc = frappe.get_doc("Rika Measurement", r.name)
            out.append(_measurement_payload(doc))
        except frappe.DoesNotExistError:
            continue
    return {"ok": True, "measurements": out}


@frappe.whitelist(allow_guest=True)
def get_measurement():
    """GET /rika/api/measurements/{name} — one recording (installer token)."""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("measurement") or "").strip()
    if not name or not frappe.db.exists("Rika Measurement", name):
        frappe.throw("Measurement not found.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Measurement", name)
    return {"ok": True, "measurement": _measurement_payload(doc)}


@frappe.whitelist(allow_guest=True)
def save_measurement():
    """POST /rika/api/measurements/save — create or update a recording (installer token).
    Body: {name?, customer_name, phone, address?, measurer?, date?, notes?, openings: [...]}"""
    _require_admin()
    body = frappe.request.get_json(silent=True) or {}
    if isinstance(body, dict) and "message" in body and isinstance(body["message"], dict):
        body = body["message"]

    name = (body.get("name") or "").strip()
    customer_name = (body.get("customer_name") or "").strip()
    phone = (body.get("phone") or "").strip()
    if not customer_name or not phone:
        frappe.throw("Customer name and phone are required.", frappe.ValidationError)
    openings = body.get("openings") or []
    if not openings or not isinstance(openings, list):
        frappe.throw("At least one opening is required.", frappe.ValidationError)

    for o in openings:
        if not (o.get("label") or "").strip():
            frappe.throw("Every opening needs a label (W01, W02…).", frappe.ValidationError)
        if not o.get("width") or not o.get("height"):
            frappe.throw("Every opening needs width and height (mm).", frappe.ValidationError)

    if name and frappe.db.exists("Rika Measurement", name):
        doc = frappe.get_doc("Rika Measurement", name)
        doc.set("openings", [])
    else:
        doc = frappe.new_doc("Rika Measurement")

    doc.customer_name = customer_name
    doc.phone = phone
    doc.address = (body.get("address") or "").strip()
    doc.measurer = (body.get("measurer") or "").strip()
    doc.date = body.get("date") or None
    doc.notes = (body.get("notes") or "").strip()
    for o in openings:
        doc.append("openings", {
            "label": (o.get("label") or "").strip(),
            "type": o.get("type") or "Sliding Window",
            "width": float(o.get("width") or 0),
            "height": float(o.get("height") or 0),
            "qty": int(o.get("qty") or 1),
            "finish": o.get("finish") or "Black",
            "glass": o.get("glass") or "Clear",
            "photo": o.get("photo") or None,
            "notes": (o.get("notes") or "").strip(),
        })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "measurement": _measurement_payload(doc)}
