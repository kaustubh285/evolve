# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate, get_link_to_form, getdate

from evolve import bot


class Workout(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from evolve.evolve.doctype.workout_cardio.workout_cardio import WorkoutCardio
		from evolve.evolve.doctype.workout_sets.workout_sets import WorkoutSets

		cardio: DF.Table[WorkoutCardio]
		duration: DF.Duration
		notes: DF.SmallText | None
		routine_name: DF.Data | None
		sets: DF.Table[WorkoutSets]
		workout_date: DF.Datetime
	# end: auto-generated types

	_DOCTYPE_NAME = "Workout"

	def after_insert(self):
		self.link_to_daily_checkin()

	def link_to_daily_checkin(self):
		"""Attach this workout to the same day's check-in, if one exists.

		Only fills an empty slot: an existing link is never overwritten, because the
		check-in's `workout` is a single Link and a second workout on the same day has
		nowhere to go. Uses db.set_value rather than loading and saving the check-in, so
		importing a workout cannot fail on unrelated check-in validation.

		When the workout is left unlinked, B1-T3 says why on the workout's timeline. A
		check-in created later still picks the workout up (`DailyCheckin.attach_days_workout`),
		so that comment records the state at import time, not now.
		"""
		if not self.workout_date:
			return

		checkin = frappe.db.get_value(
			"Daily Checkin",
			{"date": getdate(self.workout_date)},
			["name", "workout"],
			as_dict=True,
		)
		if not checkin:
			bot.log(
				self, f"workout not auto-linked, no check-in for {formatdate(getdate(self.workout_date))}"
			)
			return

		if checkin.workout:
			if checkin.workout != self.name:
				bot.log(self, f"workout not auto-linked, {checkin.name} already has {checkin.workout}")
				frappe.msgprint(
					_("{0} already has {1} attached, so {2} was left unlinked.").format(
						get_link_to_form("Daily Checkin", checkin.name),
						checkin.workout,
						self.name,
					),
					indicator="orange",
					alert=True,
				)
			return

		frappe.db.set_value("Daily Checkin", checkin.name, "workout", self.name)
		log_workout_link(self.name, checkin.name)
		frappe.msgprint(
			_("Linked to {0}.").format(get_link_to_form("Daily Checkin", checkin.name)),
			indicator="green",
			alert=True,
		)


def log_workout_link(workout: str, checkin: str):
	"""Record an automatic workout <-> check-in link on both timelines.

	Called from whichever side made the link: `Workout.link_to_daily_checkin` or
	`DailyCheckin.attach_days_workout`.
	"""
	bot.log(frappe.get_doc("Workout", workout), f"linked to {checkin}")
	bot.log(frappe.get_doc("Daily Checkin", checkin), f"attached workout {workout}")
