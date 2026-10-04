# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WorkoutCardio(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		activity: DF.Data
		distance_km: DF.Float
		duration: DF.Duration
		equipment: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	_DOCTYPE_NAME = "Workout Cardio"
