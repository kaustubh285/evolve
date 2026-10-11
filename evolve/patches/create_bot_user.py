# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Create B1-T3, the user background jobs act as. See `evolve.bot`.

Disabled with no roles and no password: it exists so jobs' edits and comments are
attributed to it, not so it can log in. Safe to re-run.
"""

import frappe

from evolve.bot import BOT_NAME, BOT_USER


def execute():
	if frappe.db.exists("User", BOT_USER):
		return

	frappe.get_doc(
		{
			"doctype": "User",
			"email": BOT_USER,
			"first_name": BOT_NAME,
			"enabled": 0,
			"send_welcome_email": 0,
			"user_type": "Website User",
		}
	).insert(ignore_permissions=True)

	frappe.db.commit()
