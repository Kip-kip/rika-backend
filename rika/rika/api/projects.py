import json
from frappe.utils import nowdate
import frappe
from .auth import _require_user

STAGES = ["Measurement", "Design", "Approval", "Fabrication", "Installation", "Handover"]
ADMIN_TOKEN_ENV = "RIKA_ADMIN_TOKEN"


def _project_payload(doc):
    sd = doc.stage_dates
    if isinstance(sd, str):
        try:
            sd = json.loads(sd)
        except (ValueError, TypeError):
            sd = {}
    if not isinstance(sd, dict):
        sd = {}

    cur_idx = STAGES.index(doc.stage) if doc.stage in STAGES else 0
    stages = []
    for i, s in enumerate(STAGES):
        stages.append({
            "stage": s,
            "index": i,
            "date": sd.get(s),
            "state": "done" if i < cur_idx else ("current" if i == cur_idx else "upcoming"),
        })

    return {
        "name": doc.name,
        "project_name": doc.project_name,
        "location": doc.location,
        "stage": doc.stage,
        "stage_index": cur_idx,
        "stages": stages,
        "deposit_paid": bool(doc.deposit_paid),
        "install_date": doc.install_date,
        "handover_date": doc.handover_date,
        "warranty_expires": doc.warranty_expires,
        "notes": doc.notes,
    }


@frappe.whitelist(allow_guest=True)
def my_projects():
    """GET /rika/api/projects — the logged-in customer's projects."""
    user = _require_user()
    cust = frappe.db.get_value("Rika Customer", {"user": user}, ["name", "phone"], as_dict=True)
    if not cust:
        return {"ok": True, "projects": []}

    phone = cust.phone
    projects = []
    # Primary: projects linked via a Rika Lead for this phone
    lead = frappe.db.get_value("Rika Lead", {"phone": phone}, "name") if phone else None
    if lead:
        for row in frappe.db.get_all("Rika Project", {"customer": lead}, order_by="creation desc"):
            projects.append(_project_payload(frappe.get_doc("Rika Project", row.name)))
    # Fallback: any project whose location embeds this phone (demo projects)
    if not projects and phone:
        for row in frappe.db.get_all("Rika Project", order_by="creation desc"):
            doc = frappe.get_doc("Rika Project", row.name)
            if (doc.location or "").strip() and phone in doc.location:
                projects.append(_project_payload(doc))
    return {"ok": True, "projects": projects}


@frappe.whitelist(allow_guest=True)
def create_demo_project():
    """POST /rika/api/projects/demo — seed a demo project for the logged-in user."""
    user = _require_user()
    cust = frappe.db.get_value("Rika Customer", {"user": user}, ["name", "first_name", "phone", "location"], as_dict=True)
    if not cust:
        frappe.throw("No Rika Customer for this user.", frappe.ValidationError)

    phone = cust.phone
    location = (cust.location or "") or (phone or cust.name)
    existing = frappe.db.get_value("Rika Project", {"project_name": "Demo — 3-Bed Windows", "location": location}, "name")
    if existing:
        return {"ok": True, "project": _project_payload(frappe.get_doc("Rika Project", existing))}

    from frappe.utils import nowdate, add_days

    base = nowdate()
    stage_dates = {
        "Measurement": base,
        "Design": add_days(base, 7),
        "Approval": add_days(base, 14),
        "Fabrication": None,
        "Installation": None,
        "Handover": None,
    }
    doc = frappe.get_doc({
        "doctype": "Rika Project",
        "naming_series": "RIKA-PROJ-",
        "project_name": "Demo — 3-Bed Windows",
        "location": location,
        "stage": "Approval",
        "stage_dates": json.dumps(stage_dates),
        "deposit_paid": 0,
        "notes": "Demo project seeded for the customer dashboard. 12 openings: 6 sliding, 4 casement, 2 fixed. Budget KSh 111,700 (from the house-map tool).",
    })
    doc.insert(ignore_permissions=True)
    return {"ok": True, "project": _project_payload(doc)}


def _require_admin():
    """Check the X-Rika-Admin-Token header against the RIKA_ADMIN_TOKEN secret.

    The secret is read from the gunicorn worker environment at request time
    (set via `bench set-env` / systemd Environment=), so it never lives in
    the repo or in site_config.
    """
    import os
    secret = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
    if not secret:
        frappe.throw("Admin API not configured (RIKA_ADMIN_TOKEN missing).", frappe.AuthenticationError)
    provided = (frappe.request.headers.get("X-Rika-Admin-Token") or "").strip()
    if provided != secret:
        frappe.throw("Invalid admin token.", frappe.AuthenticationError)


@frappe.whitelist(allow_guest=True)
def list_projects():
    """GET /rika/api/admin/projects — all projects (admin)."""
    _require_admin()
    out = []
    for row in frappe.db.get_all("Rika Project", order_by="creation desc"):
        out.append(_project_payload(frappe.get_doc("Rika Project", row.name)))
    return {"ok": True, "projects": out}


@frappe.whitelist(allow_guest=True)
def update_project():
    """POST /rika/api/admin/projects — update a project's stage (admin).

    Body: name, stage?, stage_dates? (JSON dict or object), deposit_paid?,
          install_date?, handover_date?, warranty_expires?, notes?
    stage_dates entries are merged with the existing blob; passing a date
    of "" for a stage clears that date.
    """
    _require_admin()
    d = frappe.form_dict
    name = (d.get("name") or "").strip()
    if not name or not frappe.db.exists("Rika Project", name):
        frappe.throw("Project not found.", frappe.ValidationError)

    doc = frappe.get_doc("Rika Project", name)

    # Load existing stage_dates
    sd = doc.stage_dates
    if isinstance(sd, str):
        try:
            sd = json.loads(sd)
        except (ValueError, TypeError):
            sd = {}
    if not isinstance(sd, dict):
        sd = {}

    # Merge new stage_dates if provided
    new_sd = d.get("stage_dates")
    if new_sd:
        if isinstance(new_sd, str):
            try:
                new_sd = json.loads(new_sd)
            except (ValueError, TypeError):
                frappe.throw("stage_dates must be a JSON object.", frappe.ValidationError)
        if isinstance(new_sd, dict):
            for k, v in new_sd.items():
                if k in STAGES:
                    sd[k] = (v or None) if v else None

    # Update stage
    stage = (d.get("stage") or "").strip()
    if stage:
        if stage not in STAGES:
            frappe.throw(f"Invalid stage. Must be one of: {', '.join(STAGES)}", frappe.ValidationError)
        doc.stage = stage

    # Optional fields
    if d.get("deposit_paid") is not None:
        doc.deposit_paid = 1 if str(d.get("deposit_paid")).lower() in ("1", "true", "yes") else 0
    if d.get("install_date"):
        doc.install_date = d.get("install_date")
    if d.get("handover_date"):
        doc.handover_date = d.get("handover_date")
    if d.get("warranty_expires"):
        doc.warranty_expires = d.get("warranty_expires")
    if d.get("notes") is not None:
        doc.notes = d.get("notes")

    doc.stage_dates = json.dumps(sd)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"ok": True, "project": _project_payload(frappe.get_doc("Rika Project", name))}
