# Rika M-Pesa deposit API (T-B5-07)
# STK push deposits — all M-Pesa logic lives in the rika app (no mpesa_tx).
# Credentials come from site_config (dummy values for now, swap in real Daraja creds to go live).
import base64
import json
import uuid
from datetime import datetime, timezone

import frappe
import requests
from .auth import _require_user
from .payments import _customer_projects
from .projects import _require_admin

# ---------------------------------------------------------------------------
# Config — dummy for now, swap in real Daraja creds via bench execute
# ---------------------------------------------------------------------------
DARAJA_CONFIG = {
    "short_code": "174379",
    "passkey": "REPLACE_WITH_REAL_PASSKEY",
    "consumer_key": "REPLACE_WITH_REAL_CONSUMER_KEY",
    "consumer_secret": "REPLACE_WITH_REAL_CONSUMER_SECRET",
    "callback_url": "https://dev.local/rika/api/deposits/callback",
    "env": "sandbox",
}


def _get_daraja_token():
    """Fetch (or reuse a cached) OAuth access token from Daraja."""
    ck = DARAJA_CONFIG["consumer_key"]
    cs = DARAJA_CONFIG["consumer_secret"]
    if "REPLACE" in ck or "REPLACE" in cs:
        return "DUMMY_TOKEN"
    r = requests.post(
        "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
        auth=(ck, cs),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _generate_password():
    """Base64-encode Paybill + Account + Timestamp per Safaricom spec."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{DARAJA_CONFIG['short_code']}{DARAJA_CONFIG['passkey']}{ts}"
    return base64.b64encode(raw.encode()).decode()


def _send_stk_push(phone, amount, project):
    """Call the Daraja STK Push endpoint. Returns (transaction_ref, status, error)."""
    token = _get_daraja_token()
    if token == "DUMMY_TOKEN":
        ref = f"DUMMY-{uuid.uuid4().hex[:10].upper()}"
        return ref, "completed", "dummy"  # simulate success for dev

    headers = {
        "Authorization": "***" + token,
        "Content-Type": "application/json",
    }
    payload = {
        "BusinessShortCode": DARAJA_CONFIG["short_code"],
        "Password": _generate_password(),
        "Timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "TransactionType": "Customer Pay Bill",
        "Amount": int(amount),
        "PartyA": DARAJA_CONFIG["short_code"],
        "PartyB": int(DARAJA_CONFIG["short_code"]),
        "PhoneNumber": phone.replace("+", "").replace(" ", "") if phone.startswith("+") else "254" + phone.lstrip("0"),
        "CallBackURL": DARAJA_CONFIG["callback_url"],
        "AccountReference": f"RIKA-{project}",
        "TransactionDesc": f"Rika deposit {project}",
    }
    try:
        r = requests.post("https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=payload, headers=headers, timeout=20)
        data = r.json()
        if r.status_code == 200 and data.get("ResponseCode") == 0:
            ref = data.get("CheckoutRequestID", "UNKNOWN")
            return ref, "pending", None
        return None, "failed", data.get("errorMessage") or data.get("LongMessage") or str(data)
    except Exception as e:
        return None, "failed", str(e)


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def initiate_deposit():
    """POST /rika/api/deposits/initiate — customer triggers STK push (customer token)."""
    user = _require_user()
    docs = _customer_projects(user)
    if not docs:
        frappe.throw("No project found for your account.", frappe.ValidationError)
    proj = docs[0]
    d = frappe.form_dict
    amount = float(d.get("amount") or 0)
    if amount < 50:
        frappe.throw("Minimum deposit is KSh 50.", frappe.ValidationError)

    # phone from customer record
    cust = frappe.db.get_value("Rika Customer", {"user": user}, "phone")
    if not cust:
        frappe.throw("No phone on file for your account.", frappe.ValidationError)

    ref, status, err = _send_stk_push(cust, amount, proj.name)
    if not ref:
        frappe.throw(err or "STK push failed.")

    doc = frappe.new_doc("Rika Deposit")
    doc.project = proj.name
    doc.amount = amount
    doc.transaction_ref = ref
    doc.status = "Pending" if status == "pending" else "Completed"
    if status == "completed":
        doc.paid_at = datetime.now(timezone.utc)
        doc.receipt_no = ref
    if status == "dummy":
        doc.notes = "Dummy credentials — payment simulated. Admin should mark completed after real creds are configured."
    doc.insert(ignore_permissions=True)
    return {
        "ok": True,
        "deposit": {
            "name": doc.name,
            "amount": doc.amount,
            "transaction_ref": doc.transaction_ref,
            "status": doc.status,
            "receipt_no": doc.receipt_no,
        },
        "message": "STK push sent to your phone. Complete the payment." if status == "pending" else "Deposit completed.",
    }


@frappe.whitelist(allow_guest=True)
def my_deposits():
    """GET /rika/api/deposits — customer's deposit history (customer token)."""
    user = _require_user()
    docs = _customer_projects(user)
    if not docs:
        return {"ok": True, "deposits": []}
    proj = docs[0].name
    rows = frappe.db.get_all(
        "Rika Deposit",
        filters={"project": proj},
        fields=["name", "amount", "transaction_ref", "status", "receipt_no", "paid_at"],
        order_by="creation desc",
    )
    return {"ok": True, "deposits": [dict(r) for r in rows]}


@frappe.whitelist(allow_guest=True)
def list_deposits():
    """GET /rika/api/deposits/all — all deposits for admin (admin token)."""
    _require_admin()
    rows = frappe.get_all(
        "Rika Deposit",
        fields=["name", "project", "amount", "transaction_ref", "status", "receipt_no", "paid_at"],
        order_by="creation desc",
    )
    out = []
    for r in rows:
        item = dict(r)
        try:
            p = frappe.get_doc("Rika Project", r.project)
            item["project_name"] = p.project_name
        except frappe.DoesNotExistError:
            item["project_name"] = r.project
        out.append(item)
    return {"ok": True, "deposits": out}


@frappe.whitelist(allow_guest=True)
def callback():
    """POST /rika/api/deposits/callback — Daraja STK push callback."""
    data = frappe.request.get_json(silent=True) or {}
    # Frappe wraps the body in "message" when it's a whitelested route
    body = data.get("message", data) if isinstance(data, dict) else {}

    results = body.get("CallbackMetadata") or body.get("Body", {}).get("CallbackMetadata", [])
    if not isinstance(results, list):
        return {"ok": True, "status": "ignored"}

    ref = None
    amount = None
    status_code = None
    error = None
    for r in results:
        name = r.get("Name")
        value = r.get("Value")
        if name == "MpesaReceiptNumber":
            ref = value
        elif name == "Amount":
            amount = int(value)
        elif name == "ResultCode":
            status_code = int(value)
        elif name == "ResultDesc":
            error = value

    if not ref:
        return {"ok": True, "status": "no_ref"}

    dep = frappe.db.get_value("Rika Deposit", {"transaction_ref": ref}, "name")
    if not dep:
        return {"ok": True, "status": "not_found"}

    doc = frappe.get_doc("Rika Deposit", dep)
    if status_code == 0:
        doc.status = "Completed"
        doc.receipt_no = ref
        doc.amount = amount or doc.amount
        doc.paid_at = datetime.now(timezone.utc)
    else:
        doc.status = "Failed"
        doc.notes = error
    doc.db_update()
    return {"ok": True, "status": "updated", "ref": ref}
