# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, formatdate, get_datetime, get_link_to_form, getdate

from evolve.evolve.doctype.health_event.health_event import log_health_event_link
from evolve.evolve.doctype.workout.workout import log_workout_link


class DailyCheckin(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from evolve.evolve.doctype.daily_checkin_health_event.daily_checkin_health_event import DailyCheckinHealthEvent
		from evolve.evolve.doctype.daily_checkin_meal.daily_checkin_meal import DailyCheckinMeal
		from frappe.types import DF

		date: DF.Date
		health_events: DF.TableMultiSelect[DailyCheckinHealthEvent]
		meal_entries: DF.Table[DailyCheckinMeal]
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

	def autoname(self):
		"""Name the record after the day it describes: `CHK-DD-MM-YY-00001`.

		Built from the `date` field rather than a naming series, so a check-in
		backfilled for an earlier day still carries that day's date. strftime is used
		instead of formatdate because the name must not depend on the user's display
		date format. With one check-in per day enforced, the counter is always 00001;
		it is kept for a fixed-width name.
		"""
		if not self.date:
			# mandatory validation rejects this before anything is written
			return

		self.name = make_autoname(f"CHK-{getdate(self.date).strftime('%d-%m-%y')}-.#####")

	def validate(self):
		self.ensure_one_per_day()
		self.set_total_hours()
		self.attach_days_workout()
		self.attach_days_health_events()

	def on_update(self):
		# logged here, not in validate: a new check-in doesn't exist yet during validate
		if self.flags.auto_linked_workout:
			log_workout_link(self.flags.auto_linked_workout, self.name)
			self.flags.auto_linked_workout = None

		for health_event in self.flags.auto_linked_health_events or []:
			log_health_event_link(health_event, self.name)
		self.flags.auto_linked_health_events = None

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
		# commented on in on_update, once the save has gone through
		self.flags.auto_linked_workout = self.workout

	def attach_days_health_events(self):
		"""Pick up health events that started on this date, when the check-in is created.

		Only for a new check-in. After that, `HealthEvent.after_insert` adds events as
		they're logged, and an event you take out of the table stays out instead of being
		re-added on the next save.
		"""
		if not self.is_new() or not self.date:
			return

		already = {row.health_event for row in self.health_events}
		found = frappe.get_all(
			"Health Event",
			filters={"when_started": ["between", [f"{self.date} 00:00:00", f"{self.date} 23:59:59"]]},
			pluck="name",
			order_by="when_started asc",
		)
		added = [name for name in found if name not in already]
		for name in added:
			self.append("health_events", {"health_event": name})
		# commented on in on_update, once the save has gone through
		self.flags.auto_linked_health_events = added

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
