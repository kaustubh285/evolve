# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Deterministic parser for hand-shaped workout JSON payloads.

No AI. The payload is already structured, just irregularly so: nesting depth varies
per exercise, units are baked into strings, and cardio items carry no sets. The rules
implemented here are the ones agreed in `.local/docs/v0-build-log.md` §4.

Shape handled::

    {
      "date": "2026-06-08",
      "time": "07:53",
      "workout": {
        "running":          {"type": "Treadmill", "distance": "0.79 km", "duration": "9:15"},
        "chest_press":      {"machine": {"sets": [{"weight": "25 kg", "reps": 11}, ...]}},
        "triceps_pushdown": {"cable": {"straight_bar": {"sets": [...]}}}
      }
    }

Known limitation of the format, not of this parser: exercises are object keys, so one
session cannot repeat an exercise (no supersets, no returning to a lift later).
"""

import json

import frappe
from frappe import _

#: Units we accept. Anything else raises rather than being coerced — a stray "25 lb"
#: landing silently as 25.0 is worse than an import that visibly fails.
WEIGHT_UNIT = "kg"
DISTANCE_UNIT = "km"


class WorkoutParseError(frappe.ValidationError):
	pass


def _fail(msg, *args):
	frappe.throw(_(msg).format(*args), exc=WorkoutParseError, title=_("Workout Parse Error"))


def _titleize(key):
	"""`chest_press` -> `Chest Press`, `straight_bar` -> `Straight Bar`."""
	return " ".join(part.capitalize() for part in str(key).replace("-", "_").split("_") if part)


def _measure(raw, unit, label):
	"""Parse `"25 kg"` -> `25.0`. Raise on a different unit or unparseable number."""
	if raw is None:
		return None
	if isinstance(raw, int | float):
		return float(raw)

	text = str(raw).strip()
	parts = text.split()
	if len(parts) == 2:
		number, given = parts
		if given.lower() != unit:
			_fail("{0}: expected a value in {1}, got {2!r}.", label, unit, text)
	elif len(parts) == 1:
		number = parts[0]
	else:
		_fail("{0}: cannot read {1!r}.", label, text)

	try:
		return float(number)
	except ValueError:
		_fail("{0}: cannot read {1!r} as a number.", label, text)


def _number(raw, label):
	"""Parse a bare numeric value such as an RPE. No unit expected."""
	if raw is None or raw == "":
		return None
	try:
		return float(raw)
	except (TypeError, ValueError):
		_fail("{0}: cannot read {1!r} as a number.", label, raw)


def _duration_seconds(raw, label):
	"""Parse `"9:15"` (m:ss) or `"1:09:15"` (h:mm:ss) into seconds."""
	if raw is None:
		return None
	if isinstance(raw, int | float):
		return int(raw)

	text = str(raw).strip()
	chunks = text.split(":")
	try:
		values = [int(chunk) for chunk in chunks]
	except ValueError:
		_fail("{0}: cannot read {1!r} as a duration.", label, text)

	if len(values) == 2:
		minutes, seconds = values
		hours = 0
	elif len(values) == 3:
		hours, minutes, seconds = values
	else:
		_fail("{0}: cannot read {1!r} as a duration (expected m:ss or h:mm:ss).", label, text)

	return hours * 3600 + minutes * 60 + seconds


def _find_sets(node):
	"""Descend until a dict carrying a `sets` list is found.

	Returns `(sets, path)` where `path` is the keys walked past the exercise name —
	those become `equipment`. Returns `(None, [])` when the subtree has no sets,
	which is how a cardio item is recognised.
	"""
	if not isinstance(node, dict):
		return None, []

	if "sets" in node:
		return node["sets"], []

	for key, child in node.items():
		found, path = _find_sets(child)
		if found is not None:
			return found, [key, *path]

	return None, []


def _parse_sets(exercise_key, raw_sets, equipment_path):
	exercise = _titleize(exercise_key)
	equipment = " / ".join(_titleize(segment) for segment in equipment_path) or None

	if not isinstance(raw_sets, list):
		_fail("{0}: `sets` must be a list.", exercise)

	rows = []
	for index, raw in enumerate(raw_sets, start=1):
		if not isinstance(raw, dict):
			_fail("{0}: set {1} is not an object.", exercise, index)

		label = f"{exercise} set {index}"
		# the payload calls it intensity; the schema calls it difficulty
		intensity = raw.get("intensity", raw.get("difficulty"))

		rows.append({
			"exercise": exercise,
			"equipment": equipment,
			"set_number": index,
			"weight_kg": _measure(raw.get("weight"), WEIGHT_UNIT, label),
			"reps": raw.get("reps"),
			"difficulty": _number(intensity, f"{label} intensity"),
		})
	return rows


def _parse_cardio(activity_key, node):
	activity = _titleize(activity_key)
	label = f"{activity} cardio"
	return {
		"activity": activity,
		# cardio names its equipment in a `type` value rather than a nested key
		"equipment": node.get("type") or None,
		"distance_km": _measure(node.get("distance"), DISTANCE_UNIT, label),
		"duration": _duration_seconds(node.get("duration"), label),
	}


def parse_workout_json(payload):
	"""Map a workout payload onto `Workout` + child-table field values.

	Returns a dict ready to hand to `frappe.get_doc`. Raises `WorkoutParseError`
	on anything it cannot read, rather than skipping it.
	"""
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except json.JSONDecodeError as exc:
			_fail("Payload is not valid JSON: {0}.", exc)

	if not isinstance(payload, dict):
		_fail("Payload must be a JSON object.")

	exercises = payload.get("workout")
	if not isinstance(exercises, dict) or not exercises:
		_fail("Payload has no `workout` object.")

	date = payload.get("date")
	if not date:
		_fail("Payload has no `date`.")
	time = payload.get("time")

	sets, cardio = [], []
	for key, node in exercises.items():
		raw_sets, equipment_path = _find_sets(node)
		if raw_sets is not None:
			sets.extend(_parse_sets(key, raw_sets, equipment_path))
		elif isinstance(node, dict) and ("distance" in node or "duration" in node):
			cardio.append(_parse_cardio(key, node))
		else:
			# rule 3: neither sets nor cardio measurements — refuse to guess
			_fail(
				"{0}: no `sets` and no `distance`/`duration` — cannot tell what this is.",
				_titleize(key),
			)

	return {
		"doctype": "Workout",
		"workout_date": f"{date} {time}" if time else date,
		"routine_name": payload.get("routine_name") or payload.get("routine"),
		"duration": _duration_seconds(payload.get("duration"), "Session"),
		"notes": payload.get("notes"),
		"sets": sets,
		"cardio": cardio,
	}


def create_workout_from_json(payload):
	"""Parse a payload and insert the resulting `Workout`. Returns the document."""
	return frappe.get_doc(parse_workout_json(payload)).insert()


@frappe.whitelist()
def parse_payload(payload: str) -> dict:
	"""Parse a pasted payload and return `Workout` field values for the form to fill.

	Read-only — nothing is written here. The form saves normally, so the usual
	permission checks apply at save time. Parse failures surface as the
	`WorkoutParseError` message rather than a silently half-filled form.
	"""
	values = parse_workout_json(payload)
	values.pop("doctype", None)
	return values
