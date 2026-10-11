import frappe
from frappe.utils import today

frappe.get_all("Daily Checkin", filters={"meals":["is","set"], "date":["<=",today()]}, pluck="name")


frappe.get_all("Daily Checkin Meal", {"parent": ["in", names],
  "parenttype": "Daily Checkin"}, pluck="parent", distinct=True)
