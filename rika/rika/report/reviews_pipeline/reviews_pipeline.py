import frappe

def execute(filters=None):
    columns = [
        {"fieldname": "status", "fieldtype": "Data", "label": "Status"},
        {"fieldname": "count", "fieldtype": "Int", "label": "Count"},
        {"fieldname": "avg_rating", "fieldtype": "Float", "label": "Avg Rating"},
    ]
    data = []
    reviews = frappe.db.get_all("Rika Review", fields=["status", "rating"], order_by="creation desc")
    statuses = {}
    for rev in reviews:
        status = rev.status or "Unknown"
        if status not in statuses:
            statuses[status] = {"count": 0, "rating_sum": 0}
        statuses[status]["count"] += 1
        statuses[status]["rating_sum"] += (rev.rating or 0)
    for status, counts in sorted(statuses.items()):
        data.append({
            "status": status,
            "count": counts["count"],
            "avg_rating": round(counts["rating_sum"] / counts["count"], 2) if counts["count"] > 0 else 0,
        })
    return columns, data
