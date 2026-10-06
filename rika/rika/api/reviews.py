# Rika reviews + Google Business Profile API (T-B5-12)
# Review collection: customer submits a review (site form or WhatsApp),
# Rika admin approves + posts to GBP. Admin endpoints use X-Rika-Admin-Token.
import frappe
from .projects import _require_admin


def _review_payload(doc):
    return {
        "name": doc.name,
        "customer_name": doc.customer_name,
        "phone": doc.phone,
        "project": doc.project,
        "rating": int(doc.rating or 0),
        "review_text": doc.review_text,
        "source": doc.source,
        "status": doc.status,
        "google_url": doc.google_url,
        "notes": doc.notes,
        "created": str(doc.creation),
    }


@frappe.whitelist(allow_guest=True)
def submit_review():
    """POST /rika/api/reviews/submit — customer submits a review (public, rate-limited).
    Body (form-encoded): name, phone, project?, rating (1-5), review_text, source?"""
    d = frappe.form_dict
    name = (d.get("name") or "").strip()
    phone = (d.get("phone") or "").strip()
    rating = d.get("rating")
    review_text = (d.get("review_text") or "").strip()

    if not name:
        frappe.throw("Name is required.", frappe.ValidationError)
    if not phone:
        frappe.throw("Phone is required.", frappe.ValidationError)
    if not rating or int(rating) < 1 or int(rating) > 5:
        frappe.throw("Rating must be between 1 and 5.", frappe.ValidationError)
    if not review_text:
        frappe.throw("Please write a short review.", frappe.ValidationError)

    # Prevent spam: one review per phone per 24h
    from frappe.utils import getdate, add_to_date
    cutoff = add_to_date(getdate(), days=-1)
    existing = frappe.db.exists("Rika Review", {
        "phone": phone,
        "creation": [">=", str(cutoff)],
    })
    if existing:
        frappe.throw("You've already submitted a review recently. Thank you!", frappe.ValidationError)

    project = (d.get("project") or "").strip() or None
    doc = frappe.new_doc("Rika Review")
    doc.customer_name = name
    doc.phone = phone
    doc.project = project
    doc.rating = int(rating)
    doc.review_text = review_text
    doc.source = (d.get("source") or "Site Form").strip()
    doc.status = "Pending"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"ok": True, "ref": doc.name, "message": "Thank you! We'll review your feedback shortly."}


@frappe.whitelist(allow_guest=True)
def list_reviews():
    """GET /rika/api/reviews — all reviews, newest first (installer/admin token)."""
    _require_admin()
    rows = frappe.get_all("Rika Review", order_by="creation desc", limit=200)
    out = []
    for r in rows:
        try:
            doc = frappe.get_doc("Rika Review", r.name)
            out.append(_review_payload(doc))
        except frappe.DoesNotExistError:
            continue
    return {"ok": True, "reviews": out}


@frappe.whitelist(allow_guest=True)
def update_review():
    """POST /rika/api/reviews/update — set status / google_url (admin token).
    Body: name, status?, google_url?, notes?"""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("name") or "").strip()
    if not name or not frappe.db.exists("Rika Review", name):
        frappe.throw("Review not found.", frappe.ValidationError)

    doc = frappe.get_doc("Rika Review", name)
    valid_statuses = ["Pending", "Approved", "Posted", "Rejected"]
    status = (d.get("status") or "").strip()
    if status:
        if status not in valid_statuses:
            frappe.throw("Invalid status.", frappe.ValidationError)
        doc.status = status
    google_url = (d.get("google_url") or "").strip()
    if google_url:
        doc.google_url = google_url
    notes = (d.get("notes") or "").strip()
    if notes:
        doc.notes = notes
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"ok": True, "review": _review_payload(doc)}


@frappe.whitelist(allow_guest=True)
def review_stats():
    """GET /rika/api/reviews/stats — summary for the admin dashboard (admin token)."""
    _require_admin()
    total = frappe.db.count("Rika Review")
    by_status = {}
    for s in ["Pending", "Approved", "Posted", "Rejected"]:
        by_status[s] = frappe.db.count("Rika Review", {"status": s})
    # Average rating (1-5) across all non-rejected
    rows = frappe.db.get_all("Rika Review", fields=["rating", "status"])
    rows = [r for r in rows if r.status != "Rejected"]
    ratings = [r.rating for r in rows if r.rating]
    avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None
    return {
        "ok": True,
        "total": total,
        "by_status": by_status,
        "avg_rating": avg_rating,
    }
