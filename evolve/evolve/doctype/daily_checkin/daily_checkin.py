# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, get_datetime, get_link_to_form


class DailyCheckin(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from evolve.evolve.doctype.daily_checkin_health_event.daily_checkin_health_event import (
			DailyCheckinHealthEvent,
		)
		from frappe.types import DF

		date: DF.Date
		health_events: DF.TableMultiSelect[DailyCheckinHealthEvent]
		meals: DF.Text | None
		notes: DF.SmallText | None
		protein_at_breakfast: DF.Check
		protein_at_dinner: DF.Check
		protein_at_lunch: DF.Check
		quality: DF.Rating
		sleep_end: DF.Datetime | None
		sleep_start: DF.Datetime | None
		steps: DF.Int
		total_hours: DF.Float
		workout: DF.Link | None
	# end: auto-generated types

	_DOCTYPE_NAME = "Daily Checkin"

	def validate(self):
		self.ensure_one_per_day()
		self.set_total_hours()
		self.attach_days_workout()

	def attach_days_workout(self):
		"""Pick up a workout already recorded for this date.

		The other direction is handled by `Workout.after_insert`, so the link happens
		whichever record is created first. Never overwrites an existing choice.
		"""
		if self.workout or not self.date:
			return

		self.workout = frappe.db.get_value(
			"Workout",
			{"workout_date": ["between", [f"{self.date} 00:00:00", f"{self.date} 23:59:59"]]},
			"name",
			order_by="workout_date asc",
		)

	def ensure_one_per_day(self):
		"""Enforce one check-in per calendar day.

		`unique` can't be set on a Date field, so this is checked here rather than by
		the schema. Excluding `self.name` is what lets the same record be re-saved all
		day as meals and notes are appended.
		"""
		if not self.date:
			return

		existing = frappe.db.get_value(
			"Daily Checkin", {"date": self.date, "name": ("!=", self.name)}, "name"
		)
		if existing:
			frappe.throw(
				_("A check-in already exists for {0}: {1}").format(
					formatdate(self.date), get_link_to_form("Daily Checkin", existing)
				),
				title=_("Duplicate Check-in"),
			)

	def set_total_hours(self):
		"""Derive total_hours from sleep_start/sleep_end. Never written directly."""
		if not (self.sleep_start and self.sleep_end):
			self.total_hours = 0
			return

		start = get_datetime(self.sleep_start)
		end = get_datetime(self.sleep_end)
		if end <= start:
			frappe.throw(_("Sleep End must be after Sleep Start."))

		self.total_hours = flt((end - start).total_seconds() / 3600, 2)
