// Copyright (c) 2026, devdesh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Workout", {
	refresh(frm) {
		frm.add_custom_button(__("Import from JSON"), () => confirm_then_import(frm));
	},
});

function confirm_then_import(frm) {
	const existing = (frm.doc.sets || []).length + (frm.doc.cardio || []).length;
	if (!existing) {
		show_import_dialog(frm);
		return;
	}
	frappe.confirm(
		__("This replaces the {0} set and cardio rows already on this workout. Continue?", [
			existing,
		]),
		() => show_import_dialog(frm)
	);
}

function show_import_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Import Workout from JSON"),
		size: "large",
		fields: [
			{
				fieldname: "payload",
				fieldtype: "Code",
				options: "JSON",
				label: __("Payload"),
				reqd: 1,
				description: __(
					"Sets and cardio are filled in for review. Nothing is saved until you save the form."
				),
			},
		],
		primary_action_label: __("Parse"),
		primary_action({ payload }) {
			frappe.call({
				method: "evolve.parsers.workout_json.parse_payload",
				args: { payload },
				freeze: true,
				freeze_message: __("Parsing..."),
				callback({ message }) {
					if (!message) {
						return;
					}
					apply_parsed(frm, message);
					dialog.hide();
				},
			});
		},
	});
	dialog.show();
}

function apply_parsed(frm, parsed) {
	for (const fieldname of ["workout_date", "routine_name", "duration", "notes"]) {
		if (parsed[fieldname]) {
			frm.set_value(fieldname, parsed[fieldname]);
		}
	}

	for (const [fieldname, rows] of [
		["sets", parsed.sets || []],
		["cardio", parsed.cardio || []],
	]) {
		frm.clear_table(fieldname);
		rows.forEach((row) => frm.add_child(fieldname, row));
		frm.refresh_field(fieldname);
	}

	frappe.show_alert({
		message: __("Parsed {0} sets and {1} cardio rows. Review, then save.", [
			(parsed.sets || []).length,
			(parsed.cardio || []).length,
		]),
		indicator: "green",
	});
}
