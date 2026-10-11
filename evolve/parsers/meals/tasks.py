# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Nightly job: fill each check-in's `meal_entries` from its free-text `meals`.

Runs as B1-T3 (see `evolve.bot`) and leaves a comment on every check-in it touches,
success or failure. A check-in counts as unparsed while it has `meals` text and no
`meal_entries` rows, so a failed one is simply picked up again the next night, until it
falls out of the lookback window.

Rows are only ever added to an empty table. If `meals` is edited after parsing, the
rows are not refreshed.
"""

import frappe
from frappe.utils import add_days, today

from evolve import bot
from evolve.parsers.meals.parser import parse_meals

#: How far back to look for unparsed check-ins. This also caps retries: text the model
#: can never parse gets at most this many nightly failure comments, not one forever.
LOOKBACK_DAYS = 30


def parse_unparsed_meals(lookback_days: int = LOOKBACK_DAYS) -> dict:
	"""Scheduled entry point. Returns the names parsed and failed, for `bench execute`.

	Pass a larger `lookback_days` to backfill older check-ins by hand.
	"""
	result = {"parsed": [], "failed": []}

	with bot.acting_as_bot():
		for name in checkins_to_parse(lookback_days):
			ok = parse_checkin_meals(name)
			result["parsed" if ok else "failed"].append(name)
			# one bad check-in can't undo the others
			frappe.db.commit()

	return result


def checkins_to_parse(lookback_days: int = LOOKBACK_DAYS) -> list[str]:
	"""Check-ins in the lookback window with `meals` text and no `meal_entries` rows."""
	candidates = frappe.get_all(
		"Daily Checkin",
		filters={
			"meals": ["is", "set"],
			"date": ["between", [add_days(today(), -lookback_days), today()]],
		},
		pluck="name",
		order_by="date asc",
	)
	if not candidates:
		return []

	parsed = set(
		frappe.get_all(
			"Daily Checkin Meal",
			filters={
				"parenttype": "Daily Checkin",
				"parentfield": "meal_entries",
				"parent": ["in", candidates],
			},
			pluck="parent",
			distinct=True,
		)
	)
	return [name for name in candidates if name not in parsed]


def parse_checkin_meals(name: str) -> bool:
	"""Parse one check-in's meals and save the rows. Never raises.

	Success or failure, a comment is left on the check-in. Failures also go to Error Log
	with the full traceback.
	"""
	doc = frappe.get_doc("Daily Checkin", name)
	# undo only this check-in's partial save on failure, not the whole transaction
	frappe.db.savepoint("parse_checkin_meals")

	try:
		rows = parse_meals(doc.meals, doc.date)
		for row in rows:
			doc.append("meal_entries", {**row, "source": "Parsed"})
		# B1-T3 has no roles; it's trusted to write only what this job writes
		doc.flags.ignore_permissions = True
		# `validate` still runs, e.g. a sleep_end before sleep_start fails here
		doc.save()
	except Exception as e:
		frappe.db.rollback(save_point="parse_checkin_meals")
		# frappe.throw also queues a popup message; nobody sees it in a background job
		frappe.clear_messages()
		frappe.log_error(
			title=f"Meal parsing failed: {name}", reference_doctype="Daily Checkin", reference_name=name
		)
		bot.log(doc, f"parse failed — {bot.reason(e)}")
		return False

	meals = ", ".join(row["meal"] for row in rows)
	bot.log(doc, f"parsed {len(rows)} {'meal' if len(rows) == 1 else 'meals'} — {meals}")
	return True
