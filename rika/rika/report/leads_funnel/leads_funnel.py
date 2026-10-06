import frappe

def execute(filters=None):
    columns = [
        {"fieldname": "source", "fieldtype": "Data", "label": "Source"},
        {"fieldname": "new", "fieldtype": "Int", "label": "New"},
        {"fieldname": "contacted", "fieldtype": "Int", "label": "Contacted"},
        {"fieldname": "qualified", "fieldtype": "Int", "label": "Qualified"},
        {"fieldname": "quoted", "fieldtype": "Int", "label": "Quoted"},
        {"fieldname": "won", "fieldtype": "Int", "label": "Won"},
        {"fieldname": "lost", "fieldtype": "Int", "label": "Lost"},
        {"fieldname": "total", "fieldtype": "Int", "label": "Total"},
    ]
    data = []
    leads = frappe.db.get_all("Rika Lead", fields=["source", "status"], order_by="creation desc")
    sources = {}
    for lead in leads:
        src = lead.source or "Unknown"
        if src not in sources:
            sources[src] = {"new": 0, "contacted": 0, "qualified": 0, "quoted": 0, "won": 0, "lost": 0, "total": 0}
        status = (lead.status or "New").lower()
        sources[src]["total"] += 1
        if status == "new":
            sources[src]["new"] += 1
        elif status == "contacted":
            sources[src]["contacted"] += 1
        elif status == "qualified":
            sources[src]["qualified"] += 1
        elif status == "quoted":
            sources[src]["quoted"] += 1
        elif status == "won":
            sources[src]["won"] += 1
        elif status == "lost":
            sources[src]["lost"] += 1
    for src, counts in sorted(sources.items()):
        data.append({
            "source": src,
            "new": counts["new"],
            "contacted": counts["contacted"],
            "qualified": counts["qualified"],
            "quoted": counts["quoted"],
            "won": counts["won"],
            "lost": counts["lost"],
            "total": counts["total"],
        })
    return columns, data
