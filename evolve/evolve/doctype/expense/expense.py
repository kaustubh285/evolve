# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Expense(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		category: DF.Literal["Food", "Grocery", "Shopping", "Personal", "Transfer Home", "Bills + Rent"]
		date: DF.Date | None
		notes: DF.SmallText | None
		receipt: DF.Attach | None
		skip_from_summary: DF.Check
		type: DF.Literal["Income", "Expense"]
	# end: auto-generated types

	_DOCTYPE_NAME = "Expense"
