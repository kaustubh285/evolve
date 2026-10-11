# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, formatdate, get_datetime, get_link_to_form, getdate, now_datetime

from evolve import bot


class HealthEvent(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		duration_hours: DF.Float
		meds_taken: DF.SmallText | None
		notes: DF.SmallText | None
		severity: DF.Int
		triggers: DF.SmallText | None
		until_when: DF.Datetime | None
		what_happened: DF.Literal["migraine", "headache", "sinusitis", "sore throat", "stomach ache", "back pain", "acid reflux"]
		when_started: DF.Datetime
	# end: auto-generated types

	_DOCTYPE_NAME = "Health Event"

	def validate(self):
		self.validate_severity()
		self.set_duration_hours()

	def after_insert(self):
		self.link_to_daily_checkin()

	def link_to_daily_checkin(self):
		"""Add this event to the check-in for the day it started, if one exists.

		Several events can share a day, since `health_events` is a table: this only ever
		adds a row. An event running past midnight belongs to the day it started only.

		The row is written directly rather than by loading and saving the check-in, so
		logging an event cannot fail on unrelated check-in validation, the same as
		`Workout.link_to_daily_checkin`. The other direction is handled by
		`DailyCheckin.attach_days_health_events`, so the link happens whichever record is
		created first.
		"""
		if not self.when_started:
			return

		day = getdate(self.when_started)
		checkin = frappe.db.get_value("Daily Checkin", {"date": day}, "name")
		if not checkin:
			bot.log(self, f"health event not auto-linked, no check-in for {formatdate(day)}")
			return

		existing = frappe.db.count(
			"Daily Checkin Health Event",
			{"parenttype": "Daily Checkin", "parentfield": "health_events", "parent": checkin},
		)
		frappe.get_doc(
			{
				"doctype": "Daily Checkin Health Event",
				"parenttype": "Daily Checkin",
				"parentfield": "health_events",
				"parent": checkin,
				"idx": existing + 1,
				"health_event": self.name,
			}
		).db_insert()
		# bump `modified`, so a copy of the check-in already open in a browser can't be
		# saved over the new row: Frappe rejects it as changed since it was opened
		frappe.db.set_value("Daily Checkin", checkin, "modified", now_datetime(), update_modified=False)

		log_health_event_link(self.name, checkin)
		frappe.msgprint(
			_("Linked to {0}.").format(get_link_to_form("Daily Checkin", checkin)),
			indicator="green",
			alert=True,
		)

	def validate_severity(self):
		if self.severity and not 1 <= cint(self.severity) <= 10:
			frappe.throw(_("Severity must be between 1 and 10."))

	def set_duration_hours(self):
		"""Derive duration_hours from when_started/until_when. Never written directly."""
		if not (self.when_started and self.until_when):
			self.duration_hours = 0
			return

		started = get_datetime(self.when_started)
		until = get_datetime(self.until_when)
		if until <= started:
			frappe.throw(_("Until When must be after When Started."))

		self.duration_hours = flt((until - started).total_seconds() / 3600, 2)


def log_health_event_link(health_event: str, checkin: str):
	"""Record an automatic health event <-> check-in link on both timelines.

	Called from whichever side made the link: `HealthEvent.link_to_daily_checkin` or
	`DailyCheckin.attach_days_health_events`.
	"""
	event = frappe.get_doc("Health Event", health_event)
	bot.log(event, f"linked to {checkin}")
	bot.log(
		frappe.get_doc("Daily Checkin", checkin),
		f"attached health event {health_event} ({event.what_happened})",
	)
