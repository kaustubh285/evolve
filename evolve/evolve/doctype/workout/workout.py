# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

from frappe.model.document import Document


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
