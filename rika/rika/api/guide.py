# Rika guide PDF download API
# Serves the buying guide PDF from the Frappe file manager.
import frappe

@frappe.whitelist(allow_guest=True)
def get_guide_pdf():
    """GET /api/method/rika.api.guide.get_guide_pdf — returns the guide PDF file URL (guest)."""
    file = frappe.db.get_value(
        "File",
        {"file_name": "Rika Window Buying Guide 2026.pdf"},
        ["name", "file_url"],
        as_dict=True,
    )
    if not file:
        frappe.throw("Guide PDF not found.", frappe.ValidationError)
    return {"ok": True, "url": file.file_url, "name": file.name}
