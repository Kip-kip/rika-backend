import frappe


@frappe.whitelist(allow_guest=True)
def create_booking():
    """Guest endpoint — Rika free-measurement booking form (MEAS-2).

    Route: POST /rika/api/booking  (nginx maps to
    /api/method/rika/api/bookings/create_booking).
    Maps the JSON body to a Rika Booking document.
    """
    # Read the request body: the frontend POSTs JSON (Content-Type: application/json),
    # which frappe.form_dict does NOT populate (it only covers form-encoded bodies).
    import json as _json
    try:
        raw = frappe.request.get_data(as_text=True) or ""
        data = frappe._dict(_json.loads(raw) if raw else {})
    except Exception:
        data = frappe.form_dict

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    location = (data.get("location") or "").strip()
    preferred_date = (data.get("date") or "").strip()
    if not name or not phone or not location or not preferred_date:
        frappe.throw(
            "name, phone, location and date are required", frappe.ValidationError
        )

    # Map any time value to a valid slot
    # Normalize en-dashes (–, —) to ASCII hyphens: the frontend uses "8am–12pm"
    # but the DocType option values use "8am-12pm".
    valid_slots = ["Morning (8am-12pm)", "Midday (12pm-3pm)", "Afternoon (3pm-6pm)"]
    t = (data.get("time") or "").strip()
    t = t.replace("\u2013", "-").replace("\u2014", "-").replace("–", "-").replace("—", "-")
    if t in valid_slots:
        slot = t
    else:
        # Try to infer from the time string
        hour = None
        try:
            hour = int(t.split(":")[0])
        except (ValueError, IndexError):
            hour = None
        if hour is not None:
            if hour < 12:
                slot = "Morning (8am-12pm)"
            elif hour < 15:
                slot = "Midday (12pm-3pm)"
            else:
                slot = "Afternoon (3pm-6pm)"
        else:
            slot = "Morning (8am-12pm)"

    # Sanitize source: only values allowed by the Rika Booking DocType
    allowed_sources = ["Measurement Tool", "Calculator", "Website", "WhatsApp", "Phone", "Prices Page", "Case Studies", "Case Study", "Reviews", "Locations", "Products", "Tools"]
    src = (data.get("source") or "Website").strip() or "Website"
    if src not in allowed_sources:
        src = "Website"

    width = data.get("width_cm")
    height = data.get("height_cm")
    qty = data.get("quantity")

    doc = frappe.get_doc({
        "doctype": "Rika Booking",
        "first_name": name,
        "phone": phone,
        "location": location,
        "project_type": (data.get("project_type") or "Windows").strip() or "Windows",
        "preferred_date": preferred_date,
        "preferred_time": slot,
        "width_cm": float(width) if width else None,
        "height_cm": float(height) if height else None,
        "quantity": int(qty) if qty else None,
        "notes": (data.get("notes") or "").strip() or None,
        "source": src,
        "status": "New",
    })
    doc.insert(ignore_permissions=True)

    return {
        "ok": True,
        "ref": doc.name,
        "name": doc.name,
    }
