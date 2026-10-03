import json
import frappe


@frappe.whitelist(allow_guest=True)
def save_design():
    """Guest endpoint — 'Save My Design' lead capture (SAVE-1, T-B1-03).

    Route: POST /rika/api/save-design (nginx -> /api/method/rika.rika.api.designs.save_design)

    Accepts JSON:
      name, phone, email (optional), source,
      config: { product, finish, glass, addons[], tier, width_cm, height_cm,
                quantity, estimate_low, estimate_high, notes }

    Creates:
      - Rika Design  (RIKA-DESIGN- series, config JSON, estimates)
      - Rika Lead    (or updates existing lead for the same phone) with design_config
    """
    data = frappe.form_dict

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip() or None
    if not name or not phone:
        frappe.throw("name and phone are required", frappe.ValidationError)

    # config may arrive as a JSON string (form field) or an object
    config = data.get("config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except (ValueError, TypeError):
            config = {}
    if not isinstance(config, dict):
        config = {}

    # Normalize source to a valid Rika Design source_tool option
    src = (data.get("source") or "Website").strip()
    valid_sources = ["Calculator", "Designer", "Studio", "House Map", "Measurement", "Design Studio", "Find Your Window"]
    source_tool = src if src in valid_sources else "Designer"

    # Rika Lead.source has a fixed option list; map the tool tag into a valid lead source
    # ("Find Your Window" is a real option; anything else falls back to Website).
    lead_source = source_tool if source_tool in ("Calculator", "Design Studio", "Find Your Window") else "Website"
    if (data.get("source") or "").strip() in ("Buying Guide", "WhatsApp", "Phone", "Referral"):
        lead_source = (data.get("source") or "Website").strip()

    # --- Rika Design record (the artifact) ---
    design_doc = frappe.get_doc({
        "doctype": "Rika Design",
        "naming_series": "RIKA-DESIGN-",
        "owner_name": name,
        "phone": phone,
        "source_tool": source_tool,
        "config": json.dumps(config),
        "estimate_low": float(config.get("estimate_low")) if config.get("estimate_low") else None,
        "estimate_high": float(config.get("estimate_high")) if config.get("estimate_high") else None,
        "status": "Saved",
        "notes": (config.get("notes") or data.get("notes") or "").strip() or None,
    })
    design_doc.insert(ignore_permissions=True)
    design_name = design_doc.name

    # --- Rika Lead (find or create for this phone) ---
    lead = frappe.db.get_value("Rika Lead", {"phone": phone}, "name")
    if lead:
        # Attach the new design config to the existing lead
        lead_doc = frappe.get_doc("Rika Lead", lead)
        if email:
            lead_doc.email = email
        lead_doc.design_config = design_name
        lead_doc.status = "New"
        lead_doc.db_update()
        lead_name = lead
    else:
        parts = name.split()
        lead_doc = frappe.get_doc({
            "doctype": "Rika Lead",
            "first_name": parts[0] if parts else name,
            "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
            "phone": phone,
            "email": email,
            "location": (config.get("location") or "").strip() or None,
            "window_type": (config.get("product") or "").strip() or None,
            "quantity": config.get("quantity") or None,
            "width_cm": config.get("width_cm") or None,
            "height_cm": config.get("height_cm") or None,
            "finish": (config.get("finish") or "").strip() or None,
            "glass": (config.get("glass") or "").strip() or None,
            "notes": (config.get("notes") or "").strip() or None,
            "source": lead_source,
            "status": "New",
            "design_config": design_name,
            "created_from": "save_design",
        })
        lead_doc.insert(ignore_permissions=True)
        lead_name = lead_doc.name

    return {
        "ok": True,
        "design": design_name,
        "lead": lead_name,
        "ref": design_name,
    }
