# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Rename `Daily Checkin` records from the old series to date-based names.

Old: `CHK-2026-00001` (series, creation-ordered)
New: `CHK-06-10-26-00001` (the day the check-in describes)

Safe to re-run. Nothing links *to* Daily Checkin — it only links outward to Workout
and Health Event — so no link fields need rewriting.
"""

import frappe
from frappe.utils import getdate


def execute():
	if not frappe.db.table_exists("Daily Checkin"):
		return

	for row in frappe.get_all("Daily Checkin", ["name", "date"], order_by="date asc"):
		if not row.date:
			continue

		target = f"CHK-{getdate(row.date).strftime('%d-%m-%y')}-00001"
		if row.name == target:
			continue

		if frappe.db.exists("Daily Checkin", target):
			# already taken by another record — leave this one alone rather than merge
			frappe.log_error(
				title="Daily Checkin rename skipped",
				message=f"{row.name} wanted {target}, which already exists.",
			)
			continue

		frappe.rename_doc(
			"Daily Checkin",
			row.name,
			target,
			force=True,
			show_alert=False,
			rebuild_search=False,
		)

	frappe.db.commit()
