# Rika app auth — customer accounts (T-B4-01)
import re
import frappe
from frappe import _
from frappe.utils.password import update_password, get_decrypted_password
from frappe.utils import now

# Reuse the platform JWT machinery (same secret, Redis blacklist/refresh,
# single-session per platform).
from hmis.hmis.auth.jwt_auth import (
    issue_tokens,
    validate_access_token,
    blacklist_token,
)

PHONE_RE = re.compile(r"^\+?\d{9,13}$")


def _clean_phone(phone):
    """Normalize a phone to +254XXXXXXXXX form for the User name."""
    p = re.sub(r"[^\d+]", "", phone or "")
    if not p:
        return None
    if p.startswith("0"):
        p = "+254" + p[1:]
    elif p.startswith("+"):
        pass
    elif p.startswith("254"):
        p = "+" + p
    else:
        p = "+254" + p
    digits = p.lstrip("+")
    if not 9 <= len(digits) <= 12:
        return None
    return p


def _get_customer_for_user(user):
    return frappe.db.get_value(
        "Rika Customer",
        {"user": user},
        ["name", "first_name", "last_name", "phone", "email", "location"],
        as_dict=True,
    )


def _user_payload(user):
    u = frappe.get_doc("User", user)
    cust = _get_customer_for_user(user)
    return {
        "user": user,
        "first_name": (cust.first_name if cust else u.first_name) or "",
        "last_name": (cust.last_name if cust else u.last_name) or "",
        "phone": (cust.phone if cust else u.phone) or "",
        "email": (cust.email if cust else u.email) or u.email,
        "location": (cust.location if cust else None) or "",
    }


@frappe.whitelist(allow_guest=True)
def signup():
    """POST /rika/api/auth/signup — create a customer account.

    Body: { first_name, last_name?, phone, password, email?, location? }
    Creates a Frappe User (named by normalized phone) + Rika Customer.
    Returns the user profile.
    """
    d = frappe.form_dict
    first = (d.get("first_name") or "").strip()
    last = (d.get("last_name") or "").strip()
    phone = _clean_phone(d.get("phone"))
    password = (d.get("password") or "").strip()
    email = (d.get("email") or "").strip().lower() or None
    location = (d.get("location") or "").strip() or None

    if not first:
        frappe.throw("first_name is required", frappe.ValidationError)
    if not phone:
        frappe.throw("a valid phone number is required", frappe.ValidationError)
    if len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)

    user_name = email or f"{phone.lstrip('+')}@rika-customers.local"
    user = frappe.get_all("User", filters=[{"name": ["in", [phone, user_name]]}], pluck="name")
    if user:
        frappe.throw("An account with this phone number already exists. Use the login tab.", frappe.ValidationError)

    user_name = email or f"{phone.lstrip('+')}@rika-customers.local"

    u = frappe.new_doc("User")
    u.name = user_name
    u.first_name = first
    u.last_name = last
    u.email = email or f"{phone.lstrip('+')}@rika-customers.local"
    u.phone = phone
    u.user_type = "Website User"
    u.set_new_password(password)
    u.send_welcome_email = 0
    u.flags.no_email = True
    u.save(ignore_permissions=True)

    c = frappe.new_doc("Rika Customer")
    c.user = u.name
    c.first_name = first
    c.last_name = last
    c.phone = phone
    c.email = email
    c.location = location
    c.created_at = now()
    c.insert(ignore_permissions=True)

    return {"ok": True, "user": _user_payload(user_name)}


@frappe.whitelist(allow_guest=True)
def login(usr=None, pwd=None):
    """POST /rika/api/auth/login — { phone, password } -> JWT tokens + profile.

    Mirrors the HMIS JWT flow: same secret, Redis refresh, single session
    per platform.
    """
    d = frappe.form_dict
    phone = _clean_phone(d.get("phone"))
    password = (d.get("password") or "").strip()
    platform = d.get("platform") or "desktop"

    if not phone or not password:
        frappe.throw("phone and password are required", frappe.ValidationError)

    user_name = None
    for cand in (phone, f"{phone.lstrip('+')}@rika-customers.local"):
        if frappe.db.exists("User", cand):
            user_name = cand
            break
    if not user_name:
        frappe.throw("No account found for this phone number.", frappe.AuthenticationError)

    enabled = frappe.db.get_value("User", user_name, "enabled")
    if not enabled:
        frappe.throw("This account is disabled.", frappe.AuthenticationError)

    from frappe.utils.password import passlibctx
    stored = _stored_password(user_name)
    if stored is None or not passlibctx.verify(password, stored):
        frappe.throw("Incorrect phone number or password.", frappe.AuthenticationError)

    tokens = issue_tokens(user_name, platform=platform)
    return {"ok": True, **tokens, "user": _user_payload(user_name)}


def _stored_password(user_name):
    """Read the password hash straight from the __Auth table.

    This Frappe build keeps User passwords in an un-prefixed `__Auth` table
    (not a registered doctype), so frappe.get_decrypted_password can't reach
    it. Query it directly.
    """
    try:
        rows = frappe.db.sql(
            "SELECT password FROM `__Auth` WHERE doctype=%s AND name=%s AND fieldname=%s LIMIT 1",
            ("User", user_name, "password"),
        )
        if rows and rows[0][0]:
            return rows[0][0]
    except Exception:
        pass
    try:
        return get_decrypted_password("User", user_name, raise_exception=False)
    except Exception:
        return None


def _require_user():
    """Extract and validate the Bearer token; return the user email/phone."""
    auth = (frappe.request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        frappe.throw("Missing Authorization header (Bearer token).", frappe.AuthenticationError)
    token = auth[7:].strip()
    payload = validate_access_token(token)
    user = payload.get("sub")
    if not user or not frappe.db.exists("User", user):
        frappe.throw("Invalid user in token.", frappe.AuthenticationError)
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw("This account is disabled.", frappe.AuthenticationError)
    return user


@frappe.whitelist(allow_guest=True)
def me():
    """GET /rika/api/auth/me — return the current user's profile."""
    user = _require_user()
    return {"ok": True, "user": _user_payload(user)}


@frappe.whitelist(allow_guest=True)
def logout():
    """POST /rika/api/auth/logout — blacklist the access token, clear refresh."""
    user = _require_user()
    payload = validate_access_token((frappe.request.headers.get("Authorization") or "").strip()[7:].strip())
    jti = payload.get("jti")
    if jti:
        blacklist_token(jti)

    # Access token is blacklisted; refresh tokens expire on their own
    # (Redis TTL) and are keyed opaquely, so there is nothing else to clear.
    return {"ok": True, "user": user}
