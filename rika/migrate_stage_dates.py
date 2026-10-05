"""One-time: move legacy stage_dates JSON into the per-stage Date columns."""
import json
import frappe

STAGE_FIELDS = {
    "Measurement": "date_measurement",
    "Design": "date_design",
    "Approval": "date_approval",
    "Fabrication": "date_fabrication",
    "Installation": "date_installation",
    "Handover": "date_handover",
}

def run():
    moved = 0
    for row in frappe.get_all("Rika Project", fields=["name", "stage_dates", "install_date", "handover_date"]):
        doc = frappe.get_doc("Rika Project", row.name)
        sd = row.stage_dates
        if isinstance(sd, str):
            try:
                sd = json.loads(sd)
            except (ValueError, TypeError):
                sd = {}
        if not isinstance(sd, dict):
            sd = {}
        changed = False
        for stage, field in STAGE_FIELDS.items():
            v = sd.get(stage)
            if v:
                if getattr(doc, field, None) != v:
                    setattr(doc, field, v)
                    changed = True
        # install_date / handover_date -> canonical per-stage fields if empty
        if row.install_date and not doc.date_installation:
            doc.date_installation = row.install_date
            changed = True
        if row.handover_date and not doc.date_handover:
            doc.date_handover = row.handover_date
            changed = True
        if changed:
            doc.save(ignore_permissions=True)
            moved += 1
    frappe.db.commit()
    return {"moved": moved, "total": len(frappe.get_all("Rika Project"))}
