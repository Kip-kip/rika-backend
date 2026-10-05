import frappe


class RikaProjectCost(frappe.model.document.Document):
	def before_save(self):
		self._compute()

	def _compute(self):
		cost = 0.0
		for f in (
			"cost_aluminium", "cost_glass", "cost_hardware", "cost_fabrication",
			"cost_installation", "cost_transport", "cost_wastage", "cost_marketing",
		):
			cost += float(getattr(self, f) or 0)
		self.total_cost = cost
		self.gross_profit = float(self.selling_price or 0) - cost
		self.margin_pct = (self.gross_profit / float(self.selling_price) * 100) if self.selling_price else 0
