# Rika referral API (T-B5-06)
# Post-project "Refer a friend" + reward tracking.
import frappe
from .auth import _require_user
from .projects import _require_admin
from .payments import _customer_projects


@frappe.whitelist(allow_guest=True)
def my_referrals():
    """GET /rika/api/referrals — logged-in customer's referral history (customer token)."""
    user = _require_user()
    docs = _customer_projects(user)
    if not docs:
        return {"ok": True, "referrals": []}
    proj_name = docs[0].name
    rows = frappe.db.get_all(
        "Rika Referral",
        filters={"project": proj_name},
        fields=["name", "referred_name", "referred_phone", "reward_amount", "status"],
        order_by="creation desc",
    )
    return {"ok": True, "referrals": [dict(r) for r in rows]}


@frappe.whitelist(allow_guest=True)
def create_referral():
    """POST /rika/api/referrals — customer refers a friend (customer token)."""
    user = _require_user()
    docs = _customer_projects(user)
    if not docs:
        frappe.throw("No project found for your account.", frappe.ValidationError)
    proj = docs[0]
    d = frappe.form_dict
    referred_phone = (d.get("referred_phone") or "").strip()
    if not referred_phone:
        frappe.throw("Referred phone is required.", frappe.ValidationError)
    if frappe.db.exists("Rika Referral", {"project": proj.name, "referred_phone": referred_phone}):
        frappe.throw("That number has already been referred for this project.", frappe.ValidationError)
    doc = frappe.new_doc("Rika Referral")
    doc.project = proj.name
    doc.referred_phone = referred_phone
    doc.referred_name = (d.get("referred_name") or "").strip()
    doc.reward_amount = 0
    doc.status = "Pending"
    doc.insert(ignore_permissions=True)
    return {"ok": True, "referral": {"name": doc.name, "referred_phone": doc.referred_phone, "status": doc.status}}


@frappe.whitelist(allow_guest=True)
def list_referrals():
    """GET /rika/api/referrals/all — all referrals for admin (admin token)."""
    _require_admin()
    rows = frappe.get_all("Rika Referral", fields=["name", "project", "referred_name", "referred_phone", "reward_amount", "status"], order_by="creation desc")
    out = []
    for r in rows:
        item = dict(r)
        try:
            p = frappe.get_doc("Rika Project", r.project)
            item["project_name"] = p.project_name
        except frappe.DoesNotExistError:
            item["project_name"] = r.project
        out.append(item)
    return {"ok": True, "referrals": out}


@frappe.whitelist(allow_guest=True)
def update_referral():
    """POST /rika/api/referrals/update — admin updates status/reward (admin token)."""
    _require_admin()
    d = frappe.form_dict
    name = (d.get("referral") or "").strip()
    if not name or not frappe.db.exists("Rika Referral", name):
        frappe.throw("Referral not found.", frappe.ValidationError)
    doc = frappe.get_doc("Rika Referral", name)
    if "status" in d:
        doc.status = d.get("status") or "Pending"
    if "reward_amount" in d:
        doc.reward_amount = float(d.get("reward_amount") or 0)
    doc.db_update()
    return {"ok": True, "referral": {"name": doc.name, "status": doc.status, "reward_amount": doc.reward_amount}}
