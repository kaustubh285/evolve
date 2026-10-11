# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Let B1-T3 be @mentioned, so a comment can ask it to do things. See `evolve.bot`.

Frappe only offers enabled System Users that are allowed in mentions in the @ dropdown.
A user is a System User when one of its roles has desk access, so B1-T3 gets a `Bot` role
with desk access and no doctype permissions. It still has no password, so it can't log
in. Its email notifications are turned off, or every @B1-T3 would also send an email to
its address. Safe to re-run.
"""

import frappe

from evolve.bot import BOT_ROLE, BOT_USER


def execute():
	if not frappe.db.exists("User", BOT_USER):
		# created by evolve.patches.create_bot_user, which runs first
		return

	if not frappe.db.exists("Role", BOT_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": BOT_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	user = frappe.get_doc("User", BOT_USER)
	user.enabled = 1
	user.allowed_in_mentions = 1
	if BOT_ROLE not in [row.role for row in user.roles]:
		user.append("roles", {"role": BOT_ROLE})
	# user_type follows from the role: desk access makes it a System User
	user.save(ignore_permissions=True)

	if frappe.db.exists("Notification Settings", BOT_USER):
		settings = frappe.get_doc("Notification Settings", BOT_USER)
	else:
		settings = frappe.new_doc("Notification Settings")
		settings.name = BOT_USER
	settings.enable_email_notifications = 0
	settings.enable_email_mention = 0
	settings.save(ignore_permissions=True)

	# the @ dropdown reads a cached user list
	frappe.cache.delete_value("users_for_mentions")
	frappe.db.commit()
