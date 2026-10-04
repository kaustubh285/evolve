# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime


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
