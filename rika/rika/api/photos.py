# Rika portfolio pipeline API (T-B5-04)
# Project photos per stage — customer or admin uploads, feed case-study pages.
import frappe
from .auth import _require_user
from .projects import _require_admin
from .payments import _customer_projects

STAGES = ["Measurement", "Design", "Approval", "Fabrication", "Installation", "Handover"]


def _photo_payload(doc):
    return {
        "name": doc.name,
        "project": doc.project,
        "stage": doc.stage,
        "image": doc.image,
        "caption": doc.caption,
        "published": bool(doc.published),
        "created": str(doc.creation),
    }


def _project_photos(project):
    rows = frappe.get_all("Rika Project Photo", filters={"project": project}, fields=["name"], order_by="creation asc")
    return [frappe.get_doc("Rika Project Photo", r.name) for r in rows]


@frappe.whitelist(allow_guest=True)
def my_photos():
    """GET /rika/api/photos — the customer's project photos grouped by stage (customer token)."""
    user = _require_user()
    docs = _customer_projects(user)
    out = []
    for doc in docs:
        photos = [_photo_payload(d) for d in _project_photos(doc.name)]
        out.append({"project": doc.name, "project_name": doc.project_name, "photos": photos})
    return {"ok": True, "projects": out}


@frappe.whitelist(allow_guest=True)
def upload_photo():
    """POST /rika/api/photos/upload — customer uploads a stage photo (customer token)."""
    user = _require_user()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    stage = (d.get("stage") or "").strip()
    if stage not in STAGES:
        frappe.throw("Invalid stage.", frappe.ValidationError)
    proj = frappe.db.get_value("Rika Project", project, "customer") if project else None
    if proj != user.get("customer"):
        frappe.throw("Project not found.", frappe.ValidationError)
    file = frappe.request.files.get("file")
    if not file:
        frappe.throw("No image file provided.", frappe.ValidationError)
    if not file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        frappe.throw("Only JPG, PNG or WebP images are allowed.", frappe.ValidationError)
    if len(file.read()) > 8 * 1024 * 1024:
        frappe.throw("Image too large (max 8 MB).", frappe.ValidationError)
    from frappe.utils import get_file
    doc = frappe.new_doc("Rika Project Photo")
    doc.project = project
    doc.stage = stage
    doc.caption = (d.get("caption") or "").strip()
    doc.published = 0
    file_content = file.read()
    doc.image = frappe.get_doc({
        "doctype": "File",
        "file_name": file.filename,
        "content": file_content,
        "is_private": 0,
    }).insert(ignore_permissions=True).file_url
    doc.insert(ignore_permissions=True)
    return {"ok": True, "photo": _photo_payload(doc)}


@frappe.whitelist(allow_guest=True)
def list_photos():
    """GET /rika/api/photos/all — all photos for admin/case-study use (admin token)."""
    _require_admin()
    rows = frappe.get_all("Rika Project Photo", fields=["name"], order_by="creation desc")
    out = []
    for r in rows:
        doc = frappe.get_doc("Rika Project Photo", r.name)
        item = _photo_payload(doc)
        try:
            p = frappe.get_doc("Rika Project", doc.project)
            item["project_name"] = p.project_name
            item["stage_index"] = STAGES.index(p.stage) if p.stage in STAGES else None
        except frappe.DoesNotExistError:
            item["project_name"] = doc.project
            item["stage_index"] = None
        out.append(item)
    return {"ok": True, "photos": out}


@frappe.whitelist(allow_guest=True)
def publish_photo():
    """POST /rika/api/photos/publish — mark a photo published (admin token)."""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("photo") or "").strip()
    if not name or not frappe.db.exists("Rika Project Photo", name):
        frappe.throw("Photo not found.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Project Photo", name)
    doc.published = 1 if (d.get("published") or "1") == "1" else 0
    doc.db_set("published", doc.published)
    return {"ok": True, "photo": _photo_payload(doc)}
