import frappe

def execute(filters=None):
    columns = [
        {"fieldname": "stage", "fieldtype": "Data", "label": "Stage"},
        {"fieldname": "count", "fieldtype": "Int", "label": "Count"},
        {"fieldname": "value", "fieldtype": "Currency", "label": "Value"},
    ]
    data = []
    projects = frappe.db.get_all("Rika Project", fields=["stage", "quotation"], order_by="creation desc")
    stages = {}
    for proj in projects:
        stage = proj.stage or "Unknown"
        if stage not in stages:
            stages[stage] = {"count": 0, "value": 0}
        stages[stage]["count"] += 1
        # Get the quotation total if available
        if proj.quotation:
            try:
                quote_total = frappe.db.get_value("Rika Quotation", proj.quotation, "total_low") or 0
            except Exception:
                quote_total = 0
        else:
            quote_total = 0
        stages[stage]["value"] += quote_total
    for stage, counts in sorted(stages.items()):
        data.append({
            "stage": stage,
            "count": counts["count"],
            "value": counts["value"],
        })
    return columns, data
