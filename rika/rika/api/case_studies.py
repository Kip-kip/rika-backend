# Rika case-study API (T-B5-05)
# Public project case studies built from published Rika Project Photo docs.
# One page per project; no PII (no phone, no location, no customer name).
import frappe

STAGES = ["Measurement", "Design", "Approval", "Fabrication", "Installation", "Handover"]
STAGE_LABELS = {
    "Measurement": "The Measurement",
    "Design": "The Design",
    "Installation": "Installation",
    "Handover": "Finished",
    "Fabrication": "Fabrication",
    "Approval": "Approval",
    "Cover": "Cover",
}


@frappe.whitelist(allow_guest=True)
def list_studies():
    """GET /rika/api/case-studies — public list of published case studies (no PII)."""
    published = frappe.get_all("Rika Project Photo", filters={"published": 1}, fields=["project"], distinct=True)
    out = []
    seen = set()
    for row in published:
        p = row.project
        if p in seen:
            continue
        seen.add(p)
        try:
            proj = frappe.get_doc("Rika Project", p)
        except frappe.DoesNotExistError:
            continue
        photos = frappe.get_all(
            "Rika Project Photo",
            filters={"project": p, "published": 1},
            fields=["stage", "image", "caption"],
            order_by="creation asc",
        )
        if not photos:
            continue
        cover = next((ph.image for ph in photos if ph.stage == "Cover"), photos[0].image)
        out.append({
            "project": p,
            "name": proj.project_name or p,
            "stage": proj.stage,
            "cover": cover,
            "photo_count": len(photos),
            "stages": sorted({ph.stage for ph in photos if ph.stage in STAGES}),
        })
    out.sort(key=lambda x: x["photo_count"], reverse=True)
    return {"ok": True, "studies": out}


@frappe.whitelist(allow_guest=True)
def get_study():
    """GET /rika/api/case-studies/{project} — full case study for one project (published photos only, no PII)."""
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    proj = frappe.get_doc("Rika Project", project)
    photos = frappe.get_all(
        "Rika Project Photo",
        filters={"project": project, "published": 1},
        fields=["stage", "image", "caption"],
        order_by="creation asc",
    )
    if not photos:
        frappe.throw("No published photos yet.", frappe.ValidationError)
    sections = []
    for stage in STAGES:
        stage_photos = [p for p in photos if p.stage == stage]
        if not stage_photos:
            continue
        sections.append({
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage),
            "photos": [{"image": p.image, "caption": p.caption} for p in stage_photos],
        })
    return {
        "ok": True,
        "study": {
            "project": project,
            "name": proj.project_name or project,
            "stage": proj.stage,
            "sections": sections,
        },
    }


@frappe.whitelist(allow_guest=True)
def get_project_reviews():
    """GET /rika/api/case-studies/{project}/reviews — approved reviews for a project (no PII)."""
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        return {"ok": True, "reviews": []}
    rows = frappe.get_all(
        "Rika Review",
        filters={"project": project, "status": ["in", ["Approved", "Posted"]]},
        fields=["customer_name", "rating", "review_text", "creation"],
        order_by="creation desc",
        limit=10,
    )
    out = []
    for r in rows:
        out.append({
            "name": r.customer_name,
            "rating": r.rating,
            "text": r.review_text,
            "date": str(r.creation)[:10],
        })
    return {"ok": True, "reviews": out}
