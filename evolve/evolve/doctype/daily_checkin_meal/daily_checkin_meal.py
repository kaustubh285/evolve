# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DailyCheckinMeal(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		has_caffeine: DF.Check
		has_fibre: DF.Check
		has_protein: DF.Check
		is_fried: DF.Check
		is_spicy: DF.Check
		item: DF.SmallText | None
		meal: DF.Literal["Pre-Breakfast", "Breakfast", "Brunch", "Lunch", "Afternoon Snack", "Dinner"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		source: DF.Literal["Manual", "Parsed"]
	# end: auto-generated types

	_DOCTYPE_NAME = "Daily Checkin Meal"
