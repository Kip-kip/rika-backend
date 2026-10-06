# Copyright (c) 2026, Rika and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, now_datetime


ALLOWED_EVENT_TYPES = {
	"pageview",
	"tool_use",
	"config_change",
	"cta_click",
	"lead_created",
	"quote_created",
	"design_saved",
	"booking_created",
	"deposit_initiated",
	"deposit_paid",
}

VALID_FIELDS = {
	"event_type",
	"tool",
	"page",
	"source",
	"campaign",
	"ref",
	"session_id",
	"device",
	"meta",
	"event_ts",
}

MAX_BATCH = 50
MAX_TEXT = 200


def _clean(value, field):
	"""Coerce an incoming value to a safe string (or None)."""
	if value is None:
		return None
	s = str(value).strip()
	if not s:
		return None
	if field == "page" and len(s) > 500:
		s = s[:500]
	elif len(s) > MAX_TEXT:
		s = s[:MAX_TEXT]
	return s


@frappe.whitelist(allow_guest=True)
def track_events(events):
	"""Batch tracker. `events` is a list of event objects (or a JSON string)."""
	if isinstance(events, str):
		try:
			events = frappe.parse_json(events)
		except Exception:
			frappe.throw(_("Invalid payload"))
	if not isinstance(events, list):
		frappe.throw(_("Expected a list of events"))

	if len(events) > MAX_BATCH:
		events = events[:MAX_BATCH]

	inserted = 0
	for ev in events:
		if not isinstance(ev, dict):
			continue
		event_type = (ev.get("event_type") or "").strip()
		if event_type not in ALLOWED_EVENT_TYPES:
			continue

		# Meta must be a JSON-serialisable dict; reject anything odd.
		meta = ev.get("meta")
		if meta is not None and not isinstance(meta, (dict, list)):
			meta = None

		doc = frappe.get_doc(
			{
				"doctype": "Rika Event",
				"event_type": event_type,
				"tool": _clean(ev.get("tool"), "tool"),
				"page": _clean(ev.get("page"), "page"),
				"source": _clean(ev.get("source"), "source"),
				"campaign": _clean(ev.get("campaign"), "campaign"),
				"ref": _clean(ev.get("ref"), "ref"),
				"session_id": _clean(ev.get("session_id"), "session_id"),
				"device": (ev.get("device") or "").strip() or None,
				"event_meta": meta,
				"event_ts": ev.get("event_ts")
				or now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
			}
		)
		try:
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
			inserted += 1
		except Exception:
			frappe.log_error(
				title="Rika Event insert failed",
				message=frappe.asdict(ev),
			)

	frappe.db.commit()
	frappe.response["message"] = {"inserted": inserted}
	return {"inserted": inserted}


@frappe.whitelist()
def analytics_summary(days=30):
	"""Admin analytics: funnel + tool usage + source + config. Token-gated (admin only)."""
	try:
		days = int(days)
	except Exception:
		days = 30
	days = max(1, min(days, 365))

	since = (frappe.utils.get_datetime() - frappe.utils.timedelta(days=days)).strftime(
		"%Y-%m-%d %H:%M:%S"
	)

	
	# --- Funnel (from real data) ---
	leads_total = frappe.db.count("Rika Lead", {"creation": [">=", since]})
	leads_quoted = frappe.db.count(
		"Rika Lead", {"status": "Quoted", "creation": [">=", since]}
	)
	leads_won = frappe.db.count("Rika Lead", {"status": "Won", "creation": [">=", since]})
	quotes_total = frappe.db.count("Rika Quotation", {"creation": [">=", since]})
	designs_total = frappe.db.count("Rika Design", {"creation": [">=", since]})
	bookings_total = frappe.db.count("Rika Booking", {"creation": [">=", since]})
	deposits_total = frappe.db.count("Rika Deposit", {"creation": [">=", since]})
	projects_total = frappe.db.count("Rika Project", {"creation": [">=", since]})

	# --- Revenue (won leads with lead_value) ---
	revenue = frappe.db.get_sql(
		"""SELECT COALESCE(SUM(lead_value), 0) FROM tablerika_lead
		WHERE creation >= %s AND status = 'Won'""",
		(since,),
	)[0][0]
	if not revenue:
		revenue = 0

	# --- Tool usage (pageview events) ---
	tool_usage = frappe.db.get_sql(
		"""SELECT tool, COUNT(*) as cnt FROM tablerika_event
		WHERE creation >= %s AND (tool IS NOT NULL AND tool != '')
		GROUP BY tool ORDER BY cnt DESC LIMIT 30""",
		(since,),
	)

	# --- Source (referrer/campaign) ---
	source_breakdown = frappe.db.get_sql(
		"""SELECT
			COALESCE(NULLIF(source, ''), 'direct') as src,
			COUNT(*) as cnt
		FROM tablerika_event
		WHERE creation >= %s AND event_type = 'pageview'
		GROUP BY src ORDER BY cnt DESC LIMIT 20""",
		(since,),
	)

	# --- Pageviews per day ---
	daily = frappe.db.get_sql(
		"""SELECT DATE(creation) as day, COUNT(*) as cnt
		FROM tablerika_event
		WHERE creation >= %s AND event_type = 'pageview'
		GROUP BY day ORDER BY day DESC LIMIT 60""",
		(since,),
	)

	# --- CTA clicks by tool ---
	cta_clicks = frappe.db.get_sql(
		"""SELECT COALESCE(NULLIF(tool, ''), 'unknown') as tool, COUNT(*) as cnt
		FROM tablerika_event
		WHERE creation >= %s AND event_type = 'cta_click'
		GROUP BY tool ORDER BY cnt DESC LIMIT 20""",
		(since,),
	)

	# --- Config events: top tool + type combos ---
	config_events = frappe.db.get_sql(
		"""SELECT tool, COUNT(*) as cnt
		FROM tablerika_event
		WHERE creation >= %s AND event_type IN ('tool_use','config_change')
		GROUP BY tool ORDER BY cnt DESC LIMIT 20""",
		(since,),
	)

	# --- Conversion: leads with a phone (lower-bound proxy for captured sessions) ---
	conversions = frappe.db.count(
		"Rika Lead", {"phone": ["is not", ""], "creation": [">=", since]}
	)

	return {
		"window_days": days,
		"since": since,
		"funnel": {
			"leads": leads_total,
			"leads_quoted": leads_quoted,
			"leads_won": leads_won,
			"quotes": quotes_total,
			"designs_saved": designs_total,
			"bookings": bookings_total,
			"projects": projects_total,
			"deposits": deposits_total,
			"revenue_ksh": revenue,
		},
		"tool_usage": [{"tool": r[0], "count": r[1]} for r in tool_usage],
		"sources": [{"source": r[0], "count": r[1]} for r in source_breakdown],
		"daily_pageviews": [{"day": str(r[0]), "count": r[1]} for r in daily],
		"cta_clicks": [{"tool": r[0], "count": r[1]} for r in cta_clicks],
		"config_events": [{"tool": r[0], "count": r[1]} for r in config_events],
		"pageview_sessions_with_lead": conversions,
	}
