import frappe

def execute(filters=None):
    columns = [
        {"fieldname": "project", "fieldtype": "Data", "label": "Project"},
        {"fieldname": "selling_price", "fieldtype": "Currency", "label": "Selling Price"},
        {"fieldname": "total_cost", "fieldtype": "Currency", "label": "Total Cost"},
        {"fieldname": "gross_profit", "fieldtype": "Currency", "label": "Gross Profit"},
        {"fieldname": "margin_pct", "fieldtype": "Percent", "label": "Margin %"},
    ]
    data = []
    costs = frappe.db.get_all("Rika Project Cost", fields=["project", "selling_price", "total_cost", "gross_profit", "margin_pct"], order_by="creation desc")
    for cost in costs:
        data.append({
            "project": cost.project or "N/A",
            "selling_price": cost.selling_price or 0,
            "total_cost": cost.total_cost or 0,
            "gross_profit": cost.gross_profit or 0,
            "margin_pct": cost.margin_pct or 0,
        })
    return columns, data
