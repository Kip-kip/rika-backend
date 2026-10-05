# Rika payments + documents API (T-B4-04)
#
# Customer-facing:
#   GET /rika/api/payments          -> my_payments()   project + install schedule + payment history
#   GET /rika/api/documents?doc=..  -> download_document(doc_type)  -> PDF (quote | contract | warranty)
#
# Admin (X-Rika-Admin-Token, same secret as the projects admin API):
#   POST /rika/api/admin/payments/record  -> record_payment()
import json
import html as _html
from frappe.utils import nowdate, now
import frappe
from .auth import _require_user
from .projects import STAGES, STAGE_FIELDS, _require_admin


def scrub(v):
    """Escape a value for safe HTML embedding (weasyprint)."""
    return _html.escape(str(v if v is not None else ""))

PAYMENT_METHODS = ["M-Pesa", "Bank Transfer", "Card", "Cash", "Cheque"]
PAYMENT_TYPES = ["Deposit", "Balance", "Full", "Other"]
DOC_TYPES = ["quote", "contract", "warranty"]


# ---------------------------------------------------------------------------
# resolution helpers (same chain as projects.my_projects)
# ---------------------------------------------------------------------------

def _customer_projects(user):
    """Resolve the logged-in user's Rika Project docs, newest first."""
    cust = frappe.db.get_value("Rika Customer", {"user": user}, ["name", "phone"], as_dict=True)
    if not cust:
        return []
    docs = []
    phone = cust.phone
    lead = frappe.db.get_value("Rika Lead", {"phone": phone}, "name") if phone else None
    if lead:
        for row in frappe.db.get_all("Rika Project", {"customer": lead}, order_by="creation desc"):
            docs.append(frappe.get_doc("Rika Project", row.name))
    if not docs and phone:
        for row in frappe.db.get_all("Rika Project", order_by="creation desc"):
            doc = frappe.get_doc("Rika Project", row.name)
            if (doc.location or "").strip() and phone in doc.location:
                docs.append(doc)
    return docs


def _project_schedule(doc):
    """Install schedule = the six stage dates with progress state (reused from T-B4-02)."""
    sd = {s: getattr(doc, f) for s, f in STAGE_FIELDS.items()}
    cur_idx = STAGES.index(doc.stage) if doc.stage in STAGES else 0
    out = []
    for i, s in enumerate(STAGES):
        out.append({
            "stage": s,
            "index": i,
            "date": sd.get(s),
            "state": "done" if i < cur_idx else ("current" if i == cur_idx else "upcoming"),
        })
    return out


def _payment_payload(p):
    return {
        "name": p.name,
        "payment_type": p.payment_type,
        "amount": float(p.amount or 0),
        "method": p.method,
        "status": p.status,
        "ref": p.ref,
        "paid_on": str(p.paid_on) if p.paid_on else None,
        "customer_name": p.customer_name,
    }


def _project_payments(project_name):
    rows = frappe.get_all(
        "Rika Payment",
        filters={"project": project_name},
        fields=[
            "name", "payment_type", "amount", "method", "status", "ref", "paid_on", "customer_name",
        ],
        order_by="creation asc",
    )
    return [_payment_payload(frappe._dict(r)) for r in rows]


def _project_quote(doc):
    """Return the linked Rika Quotation doc, or None."""
    if not doc.quotation:
        return None
    return frappe.get_doc("Rika Quotation", doc.quotation)


# ---------------------------------------------------------------------------
# customer-facing endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def my_payments():
    """GET /rika/api/payments — logged-in customer's project, install schedule + payment history."""
    user = _require_user()
    out = []
    for doc in _customer_projects(user):
        payments = _project_payments(doc.name)
        q = _project_quote(doc)
        totals = {"quoted_low": float(q.total_low or 0) if q else 0,
                  "quoted_high": float(q.total_high or 0) if q else 0,
                  "paid": round(sum(p["amount"] for p in payments if p["status"] == "Completed"), 2)}
        out.append({
            "name": doc.name,
            "project_name": doc.project_name,
            "location": doc.location,
            "stage": doc.stage,
            "deposit_paid": bool(doc.deposit_paid),
            "install_date": str(doc.date_installation) if doc.date_installation else None,
            "handover_date": str(doc.date_handover) if doc.date_handover else None,
            "warranty_expires": str(doc.warranty_expires) if doc.warranty_expires else None,
            "notes": doc.notes,
            "schedule": _project_schedule(doc),
            "payments": payments,
            "totals": totals,
            "has_quote": bool(doc.quotation),
            "has_contract": bool(doc.quotation),
            "has_warranty": True,
        })
    return {"ok": True, "projects": out}


def _assert_owned_project(user, project_name):
    """Ensure the requested project belongs to the logged-in user; return its doc."""
    for doc in _customer_projects(user):
        if doc.name == project_name:
            return doc
    frappe.throw("Project not found for this account.", frappe.ValidationError)


# ---------------------------------------------------------------------------
# document (PDF) generation — weasyprint via frappe.utils.pdf
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11px; color: #1a1a1a; margin: 32px; }
h1 { color: #b8741a; font-size: 22px; margin: 0 0 4px; letter-spacing: .5px; }
h2 { color: #2c2c2c; font-size: 13px; text-transform: uppercase; letter-spacing: 1px;
     border-bottom: 2px solid #e8e2d8; padding-bottom: 6px; margin: 22px 0 10px; }
.brand { color: #b8741a; font-weight: bold; font-size: 13px; letter-spacing: 2px; }
.muted { color: #777; font-size: 10px; }
table { width: 100%; border-collapse: collapse; margin-top: 8px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 10.5px; }
th { background: #161b22; color: #fff; font-weight: 600; }
tr.total td { background: #faf6ef; font-weight: bold; }
.kv { width: 100%; }
.kv td { border: none; border-bottom: 1px solid #eee; padding: 4px 2px; }
.kv td:first-child { width: 34%; color: #666; font-weight: 600; text-transform: uppercase;
                     font-size: 9.5px; letter-spacing: .5px; }
.box { border: 1px solid #e8e2d8; border-radius: 6px; padding: 12px 14px; margin: 10px 0; }
.foot { margin-top: 30px; padding-top: 10px; border-top: 1px solid #eee; font-size: 9px; color: #999; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 10px;
         font-weight: 600; }
.ok { background: #e6f4ea; color: #1e7e34; }
.warn { background: #fff4e5; color: #b35c00; }
.sign { margin-top: 46px; width: 100%; }
.sign td { border: none; border-bottom: 1px solid #333; height: 28px; }
"""


def _html_doc(body_html, title=""):
    return (
        "<html><head><meta charset='utf-8'><title>{t}</title><style>{css}</style></head>"
        "<body>{body}</body></html>"
    ).format(t=_html.escape(title or "Rika"), css=_CSS, body=body_html)


def _fmt_ksh(v):
    try:
        return "KSh {:,.0f}".format(float(v or 0))
    except Exception:
        return str(v)


def _customer_display(doc, quote=None):
    lead = frappe.db.get_value("Rika Lead", {"phone": _project_phone(doc)}, "first_name") if doc.location else None
    name = (quote.customer_name if quote and quote.customer_name else (lead or doc.project_name))
    phone = (quote.phone if quote and quote.phone else (doc.location or ""))
    return name, phone


def _project_phone(doc):
    lead = doc.customer
    if lead:
        return frappe.db.get_value("Rika Lead", lead, "phone")
    return None


def _render_quote(doc):
    q = _project_quote(doc)
    name, phone = _customer_display(doc, q)
    if q:
        items = []
        try:
            lines = json.loads(q.line_items or "[]")
        except Exception:
            lines = []
        for it in lines:
            desc = it.get("type") or it.get("description") or "Item"
            profile = it.get("profile") or ""
            if profile:
                desc = "%s — %s" % (desc, profile)
            items.append(
                "<tr><td>{d}</td><td style='text-align:center'>{q}</td>"
                "<td style='text-align:right'>{a}</td></tr>".format(
                    d=scrub(desc),
                    q=it.get("qty", 1),
                    a=_fmt_ksh(it.get("total")),
                )
            )
        items_html = "".join(items) or "<tr><td colspan='3'>No line items recorded.</td></tr>"
        total_low, total_high = _fmt_ksh(q.total_low), _fmt_ksh(q.total_high)
        ref = q.ref_code or q.name
        tier = q.tier or ""
    else:
        items_html = "<tr><td colspan='3'>No quotation has been issued for this project yet.</td></tr>"
        total_low = total_high = "—"
        ref = doc.name
        tier = ""

    body = """
<div class="brand">RIKA — ALUMINUM &amp; GLASS</div>
<h1>Quote</h1>
<table class="kv">
  <tr><td>Quote No.</td><td>{ref}</td></tr>
  <tr><td>Project</td><td>{pname} ({pno})</td></tr>
  <tr><td>Customer</td><td>{cust}</td></tr>
  <tr><td>Phone</td><td>{phone}</td></tr>
  <tr><td>Location</td><td>{loc}</td></tr>
  <tr><td>Finish / Tier</td><td>{tier}</td></tr>
  <tr><td>Date</td><td>{dt}</td></tr>
</table>
<h2>Line Items</h2>
<table>
  <tr><th>Description</th><th>Qty</th><th>Amount</th></tr>
  {items}
  <tr class="total"><td colspan="2">Estimated Total</td><td style="text-align:right">{tlow} – {thigh}</td></tr>
</table>
<div class="foot">Rika · This is a computer-generated quote. Prices are estimates and valid for 30 days from the date above.</div>
""".format(
        ref=scrub(ref), pname=scrub(doc.project_name),
        pno=scrub(doc.name), cust=scrub(name or "—"),
        phone=scrub(phone or "—"), loc=scrub(doc.location or "—"),
        tier=scrub(tier or "—"), dt=nowdate(),
        items=items_html, tlow=total_low, thigh=total_high,
    )
    return _html_doc(body, "Rika Quote {r}".format(r=ref))


def _render_contract(doc):
    q = _project_quote(doc)
    name, phone = _customer_display(doc, q)
    total = _fmt_ksh(q.total_high if q else 0)
    install = str(doc.date_installation) if doc.date_installation else "TBC"
    handover = str(doc.date_handover) if doc.date_handover else "TBC"
    warranty = str(doc.warranty_expires) if doc.warranty_expires else "12 months from handover"
    body = """
<div class="brand">RIKA — ALUMINUM &amp; GLASS</div>
<h1>Work Contract</h1>
<table class="kv">
  <tr><td>Contract No.</td><td>{pno}</td></tr>
  <tr><td>Project</td><td>{pname}</td></tr>
  <tr><td>Customer</td><td>{cust}</td></tr>
  <tr><td>Site / Location</td><td>{loc}</td></tr>
  <tr><td>Agreed Value</td><td>{val}</td></tr>
  <tr><td>Scheduled Install</td><td>{ins}</td></tr>
  <tr><td>Scheduled Handover</td><td>{hnd}</td></tr>
  <tr><td>Warranty</td><td>{war}</td></tr>
</table>
<h2>Scope of Works</h2>
<div class="box">Supply, manufacture and installation of aluminum &amp; glass works as described in
project <b>{pname}</b> at <b>{loc}</b>, in accordance with the attached quotation and the customer's
approved design. Works include fabrication, delivery, fitting, sealing and cleanup of the site on
completion.</div>
<h2>Key Terms</h2>
<ol style="font-size:10.5px; line-height:1.6">
  <li>Payment: as per the agreed schedule (deposit on approval, balance on or before handover).</li>
  <li>Schedule: installation targeted for <b>{ins}</b>, handover <b>{hnd}</b>. Dates may be adjusted by
      mutual agreement for site or weather constraints.</li>
  <li>Changes: any variation to the approved design will be quoted and requires written approval before work.</li>
  <li>Materials: aluminum profiles, glass and hardware as specified for the approved tier/finish.</li>
  <li>Warranty: {war} from the date of handover, covering fabrication and installation defects.</li>
  <li>Care &amp; maintenance: routine cleaning with non-abrasive, water-based cleaners; see the warranty
      certificate for exclusions.</li>
</ol>
<h2>Accepted &amp; Agreed</h2>
<table class="sign">
  <tr><td style="width:50%"></td><td></td></tr>
  <tr><td>Customer: {cust}</td><td>Rika — Authorized Representative</td></tr>
</table>
<div class="foot">Rika · Signed copy retained on file against project {pno}.</div>
""".format(
        pno=scrub(doc.name), pname=scrub(doc.project_name),
        cust=scrub(name or "—"), loc=scrub(doc.location or "—"),
        val=total, ins=scrub(install), hnd=scrub(handover),
        war=scrub(warranty),
    )
    return _html_doc(body, "Rika Contract {r}".format(r=doc.name))


def _render_warranty(doc):
    q = _project_quote(doc)
    name, phone = _customer_display(doc, q)
    handover = str(doc.date_handover) if doc.date_handover else (str(doc.date_installation) if doc.date_installation else "—")
    warranty = str(doc.warranty_expires) if doc.warranty_expires else "12 months from handover"
    body = """
<div class="brand">RIKA — ALUMINUM &amp; GLASS</div>
<h1>Warranty Certificate</h1>
<table class="kv">
  <tr><td>Certificate No.</td><td>{pno}-W</td></tr>
  <tr><td>Project</td><td>{pname}</td></tr>
  <tr><td>Customer</td><td>{cust}</td></tr>
  <tr><td>Location</td><td>{loc}</td></tr>
  <tr><td>Handover</td><td>{hnd}</td></tr>
  <tr><td>Warranty Period</td><td>{war}</td></tr>
</table>
<h2>What This Warranty Covers</h2>
<div class="box">Rika warrants the aluminum profiles, glass, hardware and installation of the works listed
above against defects in materials and workmanship from the date of handover until <b>{war}</b>,
inclusive.</div>
<h2>Exclusions</h2>
<ol style="font-size:10.5px; line-height:1.6">
  <li>Damage from impact, misuse, force majeure, or unauthorized alteration.</li>
  <li>Normal wear of seals/hardware beyond reasonable use, and glass breakage from external force.</li>
  <li>Damage caused by poor site drainage, structural movement or third-party works.</li>
  <li>Failure to follow the care &amp; maintenance guidance (non-abrasive cleaning, unobstructed operation).</li>
</ol>
<h2>Claim Process</h2>
<div class="box">Report the defect within the warranty period with your project reference <b>{pno}</b>. Rika will
inspect and, where the defect is covered, repair or replace the affected component at no charge.</div>
<table class="sign">
  <tr><td style="width:50%"></td><td></td></tr>
  <tr><td>Issued by Rika</td><td>Customer: {cust}</td></tr>
</table>
<div class="foot">Rika · Computer-generated warranty certificate for project {pno}.</div>
""".format(
        pno=scrub(doc.name), pname=scrub(doc.project_name),
        cust=scrub(name or "—"), loc=scrub(doc.location or "—"),
        hnd=scrub(handover), war=scrub(warranty),
    )
    return _html_doc(body, "Rika Warranty {r}".format(r=doc.name))


_DOC_RENDERERS = {
    "quote": _render_quote,
    "contract": _render_contract,
    "warranty": _render_warranty,
}
_DOC_FILENAMES = {
    "quote": "Rika-Quote-{n}.pdf",
    "contract": "Rika-Contract-{n}.pdf",
    "warranty": "Rika-Warranty-{n}.pdf",
}


@frappe.whitelist(allow_guest=True)
def download_document():
    """GET /rika/api/documents?doc=quote|contract|warranty&project=RIKA-PROJ-xxx
    Returns the customer's own project document as a PDF download."""
    user = _require_user()
    d = frappe.form_dict
    doc_type = (d.get("doc") or "").strip().lower()
    project = (d.get("project") or "").strip()
    if doc_type not in DOC_TYPES:
        frappe.throw("Unknown document type.", frappe.ValidationError)

    doc = None
    for cand in _customer_projects(user):
        if not project or cand.name == project:
            doc = cand
            break
    if not doc:
        frappe.throw("Project not found for this account.", frappe.ValidationError)

    # availability gates
    if doc_type in ("quote", "contract") and not doc.quotation:
        frappe.throw("No quote exists for this project yet.", frappe.ValidationError)

    from frappe.utils.pdf import get_pdf
    html = _DOC_RENDERERS[doc_type](doc)
    pdf = get_pdf(html)
    filename = _DOC_FILENAMES[doc_type].format(n=doc.name)

    from werkzeug.wrappers import Response as _WZResponse
    return _WZResponse(
        response=pdf,
        status=200,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# admin endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def record_payment():
    """POST /rika/api/admin/payments/record — record a payment against a project (admin)."""
    _require_admin()
    d = frappe.form_dict
    project = (d.get("project") or "").strip()
    if not project or not frappe.db.exists("Rika Project", project):
        frappe.throw("Project not found.", frappe.ValidationError)
    pdoc = frappe.get_doc("Rika Project", project)
    ptype = (d.get("payment_type") or "Deposit").strip()
    if ptype not in PAYMENT_TYPES:
        frappe.throw("Invalid payment_type.", frappe.ValidationError)
    method = (d.get("method") or "M-Pesa").strip()
    if method not in PAYMENT_METHODS:
        frappe.throw("Invalid method.", frappe.ValidationError)

    lead = pdoc.customer
    customer_name = phone = None
    if lead:
        customer_name = frappe.db.get_value("Rika Lead", lead, "first_name")
        phone = frappe.db.get_value("Rika Lead", lead, "phone")

    doc = frappe.get_doc({
        "doctype": "Rika Payment",
        "project": project,
        "customer_name": customer_name,
        "phone": phone,
        "payment_type": ptype,
        "amount": float(d.get("amount") or 0),
        "method": method,
        "status": (d.get("status") or "Completed").strip(),
        "ref": (d.get("ref") or "").strip(),
        "paid_on": (d.get("paid_on") or nowdate()).strip(),
        "notes": (d.get("notes") or "").strip(),
    })
    doc.insert(ignore_permissions=True)

    # a Completed Deposit payment flags the project's deposit
    if ptype == "Deposit" and doc.status == "Completed" and not pdoc.deposit_paid:
        pdoc.deposit_paid = 1
        pdoc.save(ignore_permissions=True)

    return {"ok": True, "payment": _payment_payload(doc)}
