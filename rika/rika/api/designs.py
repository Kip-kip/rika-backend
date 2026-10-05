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


@frappe.whitelist(allow_guest=True)
def list_my_designs():
    """GET /rika/api/my-designs — the logged-in customer's saved designs."""
    from .auth import _require_user

    user = _require_user()
    phone = frappe.db.get_value("Rika Customer", {"user": user}, "phone")
    if not phone:
        return {"ok": True, "designs": []}

    out = []
    for row in frappe.get_all(
        "Rika Design",
        {"phone": phone},
        ["name", "source_tool", "config", "estimate_low", "estimate_high", "saved_at", "status", "notes"],
        order_by="creation desc",
        limit=50,
    ):
        cfg = {}
        if row.config:
            try:
                cfg = json.loads(row.config)
            except (ValueError, TypeError):
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        out.append({
            "name": row.name,
            "source_tool": row.source_tool,
            "saved_at": row.saved_at,
            "status": row.status,
            "notes": row.notes,
            "product": cfg.get("product"),
            "width_cm": cfg.get("width_cm"),
            "height_cm": cfg.get("height_cm"),
            "quantity": cfg.get("quantity"),
            "finish": cfg.get("finish"),
            "glass": cfg.get("glass"),
            "tier": cfg.get("tier"),
            "addons": cfg.get("addons"),
            "estimate_low": row.estimate_low,
            "estimate_high": row.estimate_high,
        })
    return {"ok": True, "designs": out}
