// Copyright (c) 2026, devdesh and contributors
// For license information, please see license.txt

// Wake time is the same nearly every day, so it is prefilled rather than picked.
// Change it here if your usual alarm moves.
const DEFAULT_WAKE = "06:45:00";

frappe.ui.form.on("Daily Checkin", {
	refresh(frm) {
		prefill_sleep_end(frm);
		frm.add_custom_button(__("Sleep Times"), () => show_sleep_dialog(frm));
	},

	date(frm) {
		// the date decides which morning sleep_end belongs to
		prefill_sleep_end(frm);
	},
});

function prefill_sleep_end(frm) {
	if (!frm.is_new() || !frm.doc.date || frm.doc.sleep_end) {
		return;
	}
	frm.set_value("sleep_end", `${frm.doc.date} ${DEFAULT_WAKE}`);
}

// Entering two datetimes through the calendar picker is the fiddliest part of the
// form, and the date is already on the record. This asks for two *times* instead and
// works out the dates: if you fell asleep later in the clock-day than you woke, that
// was the night before.
function show_sleep_dialog(frm) {
	if (!frm.doc.date) {
		frappe.msgprint(__("Set the check-in date first."));
		return;
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Sleep Times"),
		fields: [
			{
				fieldname: "slept_at",
				fieldtype: "Time",
				label: __("Fell asleep"),
				default: time_part(frm.doc.sleep_start) || "23:00:00",
			},
			{
				fieldname: "woke_at",
				fieldtype: "Time",
				label: __("Woke up"),
				default: time_part(frm.doc.sleep_end) || DEFAULT_WAKE,
				description: __("Dates are worked out from the check-in date."),
			},
		],
		primary_action_label: __("Apply"),
		primary_action({ slept_at, woke_at }) {
			if (!slept_at || !woke_at) {
				frappe.msgprint(__("Both times are needed."));
				return;
			}

			// fell asleep at or after the wake time on the clock => it was yesterday
			const slept_date =
				slept_at >= woke_at ? frappe.datetime.add_days(frm.doc.date, -1) : frm.doc.date;

			frm.set_value("sleep_start", `${slept_date} ${slept_at}`);
			frm.set_value("sleep_end", `${frm.doc.date} ${woke_at}`);
			dialog.hide();
		},
	});
	dialog.show();
}

function time_part(value) {
	return value && value.includes(" ") ? value.split(" ")[1] : null;
}
