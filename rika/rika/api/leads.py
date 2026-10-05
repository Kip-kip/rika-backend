import frappe


@frappe.whitelist(allow_guest=True)
def create_lead():
    """Guest endpoint — Rika website quote form.

    Registered as a custom API at /api/method/rika_api/create_lead
    (allow-guest via custom_api + api_permissions, NOT the blocked
    /api/method/ gate). Maps the JSON body to a Rika Lead document.
    """
    data = frappe.form_dict

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not name or not phone:
        frappe.throw("name and phone are required", frappe.ValidationError)

    doc = frappe.get_doc({
        "doctype": "Rika Lead",
        "first_name": name,
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
        "source": (data.get("source") or "Website").strip() or "Website",
        "status": "New",
    })
    doc.insert(ignore_permissions=True)

    return {
        "ok": True,
        "ref": (data.get("ref") or "").strip() or doc.name,
        "name": doc.name,
    }
