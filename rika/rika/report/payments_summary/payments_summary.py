import frappe

def execute(filters=None):
    columns = [
        {"fieldname": "status", "fieldtype": "Data", "label": "Status"},
        {"fieldname": "count", "fieldtype": "Int", "label": "Count"},
        {"fieldname": "total", "fieldtype": "Currency", "label": "Total"},
        {"fieldname": "avg", "fieldtype": "Currency", "label": "Avg"},
    ]
    data = []
    payments = frappe.db.get_all("Rika Payment", fields=["status", "amount"], order_by="creation desc")
    statuses = {}
    for pay in payments:
        status = pay.status or "Unknown"
        if status not in statuses:
            statuses[status] = {"count": 0, "total": 0}
        statuses[status]["count"] += 1
        statuses[status]["total"] += (pay.amount or 0)
    for status, counts in sorted(statuses.items()):
        data.append({
            "status": status,
            "count": counts["count"],
            "total": counts["total"],
            "avg": round(counts["total"] / counts["count"], 2) if counts["count"] > 0 else 0,
        })
    return columns, data
