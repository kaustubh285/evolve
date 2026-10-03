# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WorkoutSets(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		difficulty: DF.Float
		equipment: DF.Data | None
		exercise: DF.Data
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		reps: DF.Int
		set_number: DF.Int
		weight_kg: DF.Float
	# end: auto-generated types

	_DOCTYPE_NAME = "Workout Sets"
