import frappe


@frappe.whitelist(allow_guest=True)
def create_quotation():
    """Guest endpoint — Rika quote form → Rika Quotation.

    Route: POST /rika/api/quote  (nginx → /api/method/rika/api/quotations/create_quotation)
    Accepts JSON body; maps to a Rika Quotation document.
    """
    data = frappe.form_dict

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not name or not phone:
        frappe.throw("name and phone are required", frappe.ValidationError)

    # Try to find an existing lead for this phone
    lead = frappe.db.get_value("Rika Lead", {"phone": phone}, "name")

    # If no lead, create one (best effort — don't block the quote)
    if not lead:
        try:
            lead_doc = frappe.get_doc({
                "doctype": "Rika Lead",
                "first_name": name.split()[0] if name else "",
                "last_name": " ".join(name.split()[1:]) if " " in name else "",
                "phone": phone,
                "email": (data.get("email") or "").strip() or None,
                "location": (data.get("location") or "").strip() or None,
                "window_type": (data.get("type") or "").strip() or None,
                "quantity": data.get("quantity") or None,
                "width_cm": data.get("width") or None,
                "height_cm": data.get("height") or None,
                "finish": (data.get("finish") or "").strip() or None,
                "glass": (data.get("glass") or "").strip() or None,
                "notes": (data.get("notes") or "").strip() or None,
                "source": "Website",
                "status": "New",
            })
            lead_doc.insert(ignore_permissions=True)
            lead = lead_doc.name
        except Exception:
            lead = None

    # Build line_items JSON (single line for now; multi-line later)
    qty = data.get("quantity")
    width = data.get("width")
    height = data.get("height")
    line = {
        "type": (data.get("type") or "").strip(),
        "width_m": float(width) if width else None,
        "height_m": float(height) if height else None,
        "qty": int(qty) if qty else 1,
        "profile": (data.get("finish") or "").strip() or None,
        "glass": (data.get("glass") or "").strip() or None,
        "finish": (data.get("finish") or "").strip() or None,
    }
    import json
    line_items = json.dumps([line])

    # Estimate totals (rough: use a flat rate per m² as placeholder)
    total_low = data.get("total_low")
    total_high = data.get("total_high")
    try:
        total_low = float(total_low) if total_low else 0
        total_high = float(total_high) if total_high else 0
    except (ValueError, TypeError):
        total_low = total_high = 0

    doc = frappe.get_doc({
        "doctype": "Rika Quotation",
        "naming_series": "RIKA-QUOTE-",
        "lead": lead,
        "customer_name": name,
        "phone": phone,
        "location": (data.get("location") or "").strip() or None,
        "tier": (data.get("tier") or "Comfort").strip() or "Comfort",
        "line_items": line_items,
        "total_low": total_low,
        "total_high": total_high,
        "ref_code": (data.get("ref") or "").strip() or None,
        "status": "Draft",
        "notes": (data.get("notes") or "").strip() or None,
    })
    doc.insert(ignore_permissions=True)

    return {
        "ok": True,
        "ref": (data.get("ref") or "").strip() or doc.name,
        "name": doc.name,
    }


@frappe.whitelist(allow_guest=True)
def list_my_quotations():
    """GET /rika/api/my-quotations — the logged-in customer's quotations."""
    import json
    from .auth import _require_user

    user = _require_user()
    phone = frappe.db.get_value("Rika Customer", {"user": user}, "phone")
    if not phone:
        return {"ok": True, "quotations": []}

    out = []
    for row in frappe.get_all(
        "Rika Quotation",
        {"phone": phone},
        ["name", "customer_name", "location", "tier", "line_items", "total_low", "total_high", "ref_code", "status", "submitted_at", "notes"],
        order_by="creation desc",
        limit=50,
    ):
        items = []
        if row.line_items:
            try:
                raw = json.loads(row.line_items)
                if isinstance(raw, list):
                    items = raw
            except (ValueError, TypeError):
                items = []
        out.append({
            "name": row.name,
            "ref_code": row.ref_code,
            "customer_name": row.customer_name,
            "location": row.location,
            "tier": row.tier,
            "total_low": row.total_low,
            "total_high": row.total_high,
            "status": row.status,
            "submitted_at": row.submitted_at,
            "notes": row.notes,
            "line_items": items,
        })
    return {"ok": True, "quotations": out}
