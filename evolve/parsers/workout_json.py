# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Deterministic parsers for workout exports. No AI.

Three shapes are accepted, dispatched on content:

**1. Strong share text** — what the app's share button produces::

    Early Morning Workout
    Tuesday, 6 October 2026 at 07:27

    Running (Treadmill)
    Set 1: 0.72 km | 9:45

    Chest Fly
    Set 1: 25 kg x 11
    Set 2: 32 kg x 11 @ 7

**2. `workout_log` JSON** — exercises as a list, equipment in the name::

    {"workout_log": {"date": "2026-10-06", "time": "07:27", "exercises": [
        {"name": "Running (Treadmill)", "set_1": {"distance": "0.72 km", "time": "9:45"}},
        {"name": "Chest Fly", "sets": [{"weight": "25 kg", "reps": 11}]}
    ]}}

**3. Legacy nested JSON** — exercises as object keys, equipment as nesting::

    {"date": "2026-06-08", "time": "07:53", "workout": {
        "chest_press": {"machine": {"sets": [{"weight": "25 kg", "reps": 11}]}},
        "triceps_pushdown": {"cable": {"straight_bar": {"sets": [...]}}}
    }}

Shape 3 cannot represent a repeated exercise in one session (exercises are object
keys), so supersets and returning to a lift only survive shapes 1 and 2.

Whether a block is strength or cardio is decided by its *content* — weight/reps versus
distance/duration — never by its name. A block with neither raises rather than being
guessed at or skipped.
"""

import json
import re
from calendar import month_abbr, month_name

import frappe
from frappe import _

#: Accepted units. Anything else raises rather than being coerced — a stray "25 lb"
#: landing silently as 25.0 is worse than an import that visibly fails.
WEIGHT_UNIT = "kg"
DISTANCE_UNIT = "km"

#: Keys that have all meant "how hard was that set" across these exports. `rest` comes
#: from the `workout_log` shape, where it holds the text format's `@ 7` annotation.
INTENSITY_KEYS = ("intensity", "rpe", "difficulty", "rest")

_MONTHS = {
	**{name.lower(): num for num, name in enumerate(month_name) if name},
	**{abbr.lower(): num for num, abbr in enumerate(month_abbr) if abbr},
}

# "Set 1: 0.72 km | 9:45"
_CARDIO_SET = re.compile(
	r"^set\s*(\d+)\s*:\s*([\d.]+)\s*([a-z]+)\s*\|\s*([\d:]+)\s*$", re.I
)
# "Set 2: 32 kg x 11 @ 7"  (x may be the multiplication sign)
_WEIGHT_SET = re.compile(
	r"^set\s*(\d+)\s*:\s*([\d.]+)\s*([a-z]+)\s*[x×*]\s*(\d+)\s*(?:@\s*([\d.]+))?\s*$", re.I
)
# "Set 1: 11 reps @ 8"  (bodyweight)
_REPS_SET = re.compile(r"^set\s*(\d+)\s*:\s*(\d+)\s*reps?\s*(?:@\s*([\d.]+))?\s*$", re.I)
_SET_LINE = re.compile(r"^set\s*\d+\s*:", re.I)
_DATE_LINE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:.*?(\d{1,2}):(\d{2}))?")
_SET_KEY = re.compile(r"^set[_\s-]*(\d+)$", re.I)


class WorkoutParseError(frappe.ValidationError):
	pass


def _fail(msg, *args):
	frappe.throw(_(msg).format(*args), exc=WorkoutParseError, title=_("Workout Parse Error"))


# ---------------------------------------------------------------- value parsing


def _titleize(key):
	"""`chest_press` -> `Chest Press`, `straight_bar` -> `Straight Bar`."""
	return " ".join(part.capitalize() for part in str(key).replace("-", "_").split("_") if part)


def _measure(raw, unit, label):
	"""Parse `"25 kg"` -> `25.0`. Raise on a different unit or unparseable number."""
	if raw is None or raw == "":
		return None
	if isinstance(raw, int | float):
		return float(raw)

	text = str(raw).strip()
	parts = text.split()
	if len(parts) == 2:
		number, given = parts
		if given.lower() != unit:
			_fail("{0}: expected a value in {1}, got {2}.", label, unit, text)
	elif len(parts) == 1:
		number = parts[0]
	else:
		_fail("{0}: cannot read {1}.", label, text)

	try:
		return float(number)
	except ValueError:
		_fail("{0}: cannot read {1} as a number.", label, text)


def _number(raw, label):
	"""Parse a bare numeric value such as an RPE. No unit expected."""
	if raw is None or raw == "":
		return None
	try:
		return float(raw)
	except (TypeError, ValueError):
		_fail("{0}: cannot read {1} as a number.", label, raw)


def _duration_seconds(raw, label):
	"""Parse `"9:15"` (m:ss) or `"1:09:15"` (h:mm:ss) into seconds."""
	if raw is None or raw == "":
		return None
	if isinstance(raw, int | float):
		return int(raw)

	text = str(raw).strip()
	try:
		values = [int(chunk) for chunk in text.split(":")]
	except ValueError:
		_fail("{0}: cannot read {1} as a duration.", label, text)

	if len(values) == 1:
		return values[0] * 60  # a bare number of minutes
	if len(values) == 2:
		minutes, seconds = values
		hours = 0
	elif len(values) == 3:
		hours, minutes, seconds = values
	else:
		_fail("{0}: cannot read {1} as a duration (expected m:ss or h:mm:ss).", label, text)

	return hours * 3600 + minutes * 60 + seconds


def _split_name(name):
	"""`Triceps Pushdown (Cable - Straight Bar)` -> `("Triceps Pushdown", "Cable / Straight Bar")`.

	The separator is a *spaced* hyphen or a slash, so hyphenated equipment such as
	`T-Bar` survives intact.
	"""
	text = str(name or "").strip()
	if not text:
		_fail("An exercise has no name.")

	match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text)
	if not match:
		return text, None

	exercise = match.group(1).strip() or text
	segments = [s.strip() for s in re.split(r"\s+-\s+|\s*/\s*", match.group(2)) if s.strip()]
	return exercise, " / ".join(segments) or None


def _intensity_of(raw):
	for key in INTENSITY_KEYS:
		if raw.get(key) not in (None, ""):
			return raw[key]
	return None


# ------------------------------------------------------------------ row builders


def _strength_row(exercise, equipment, index, raw, label):
	return {
		"exercise": exercise,
		"equipment": equipment,
		"set_number": index,
		"weight_kg": _measure(raw.get("weight"), WEIGHT_UNIT, label),
		"reps": raw.get("reps"),
		"difficulty": _number(_intensity_of(raw), f"{label} intensity"),
	}


def _cardio_row(activity, equipment, raw, label):
	return {
		"activity": activity,
		"equipment": equipment,
		"distance_km": _measure(raw.get("distance"), DISTANCE_UNIT, label),
		# the `workout_log` shape calls the elapsed time `time`
		"duration": _duration_seconds(raw.get("duration") or raw.get("time"), label),
	}


def _is_cardio(raw):
	return any(raw.get(k) not in (None, "") for k in ("distance", "duration", "time")) and not any(
		raw.get(k) not in (None, "") for k in ("weight", "reps")
	)


def _is_strength(raw):
	return any(raw.get(k) not in (None, "") for k in ("weight", "reps"))


# --------------------------------------------------------- shape 1: share text


def _parse_datetime_line(line):
	match = _DATE_LINE.search(line)
	if not match:
		return None

	day, month_text, year, hour, minute = match.groups()
	month = _MONTHS.get(month_text.lower())
	if not month:
		return None

	stamp = f"{int(year):04d}-{month:02d}-{int(day):02d}"
	if hour and minute:
		stamp += f" {int(hour):02d}:{int(minute):02d}:00"
	return stamp


def _parse_share_text(text):
	"""Parse the Strong app's share text (shape 1)."""
	lines = [line.strip() for line in text.splitlines()]
	lines = [line for line in lines if line and not line.lower().startswith(("http://", "https://"))]
	if not lines:
		_fail("Payload is empty.")

	routine_name = None
	workout_date = None
	body_start = 0

	for index, line in enumerate(lines[:3]):
		stamp = _parse_datetime_line(line)
		if stamp:
			workout_date = stamp
			body_start = index + 1
			break
		if routine_name is None and not _SET_LINE.match(line):
			routine_name = line

	if not workout_date:
		_fail(
			"Could not find a date line. Expected something like "
			"'Tuesday, 6 October 2026 at 07:27'."
		)

	sets, cardio = [], []
	exercise = equipment = None

	for line in lines[body_start:]:
		if not _SET_LINE.match(line):
			exercise, equipment = _split_name(line)
			continue

		if not exercise:
			_fail("Found the set line {0} before any exercise name.", line)

		label = f"{exercise} {line}"

		match = _CARDIO_SET.match(line)
		if match:
			_, distance, unit, elapsed = match.groups()
			cardio.append(
				_cardio_row(exercise, equipment, {"distance": f"{distance} {unit}", "time": elapsed}, label)
			)
			continue

		match = _WEIGHT_SET.match(line)
		if match:
			index, weight, unit, reps, intensity = match.groups()
			sets.append(
				_strength_row(
					exercise, equipment, int(index),
					{"weight": f"{weight} {unit}", "reps": int(reps), "intensity": intensity},
					label,
				)
			)
			continue

		match = _REPS_SET.match(line)
		if match:
			index, reps, intensity = match.groups()
			sets.append(
				_strength_row(
					exercise, equipment, int(index),
					{"reps": int(reps), "intensity": intensity},
					label,
				)
			)
			continue

		_fail("{0}: cannot read the set line {1}.", exercise, line)

	if not sets and not cardio:
		_fail("No sets found in the payload.")

	return {
		"doctype": "Workout",
		"workout_date": workout_date,
		"routine_name": routine_name,
		"duration": None,
		"notes": None,
		"sets": sets,
		"cardio": cardio,
	}


# ------------------------------------------------- shape 2: exercises as a list


def _ordered_set_keys(block):
	found = []
	for key in block:
		match = _SET_KEY.match(str(key))
		if match and isinstance(block[key], dict):
			found.append((int(match.group(1)), key))
	return [key for _, key in sorted(found)]


def _parse_exercise_list(payload):
	"""Parse the `workout_log` shape (shape 2)."""
	date = payload.get("date")
	if not date:
		_fail("Payload has no `date`.")
	time = payload.get("time")

	sets, cardio = [], []

	for block in payload["exercises"]:
		if not isinstance(block, dict):
			_fail("Each entry in `exercises` must be an object.")

		exercise, equipment = _split_name(block.get("name"))

		raw_sets = block.get("sets")
		if isinstance(raw_sets, list):
			rows = [(index, raw) for index, raw in enumerate(raw_sets, start=1)]
		else:
			keys = _ordered_set_keys(block)
			if not keys:
				_fail(
					"{0}: no `sets` list and no `set_1` object — cannot tell what this is.",
					exercise,
				)
			rows = [(index, block[key]) for index, key in enumerate(keys, start=1)]

		for index, raw in rows:
			if not isinstance(raw, dict):
				_fail("{0}: set {1} is not an object.", exercise, index)

			label = f"{exercise} set {index}"
			if _is_strength(raw):
				sets.append(_strength_row(exercise, equipment, index, raw, label))
			elif _is_cardio(raw):
				cardio.append(_cardio_row(exercise, equipment, raw, label))
			else:
				_fail(
					"{0}: set {1} has no weight/reps and no distance/duration — "
					"cannot tell what this is.",
					exercise,
					index,
				)

	return {
		"doctype": "Workout",
		"workout_date": f"{date} {time}" if time else date,
		"routine_name": payload.get("routine_name") or payload.get("routine") or payload.get("name"),
		"duration": _duration_seconds(payload.get("duration"), "Session"),
		"notes": payload.get("notes"),
		"sets": sets,
		"cardio": cardio,
	}


# ---------------------------------------------- shape 3: legacy nested objects


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


def _parse_nested(payload):
	"""Parse the original nested shape (shape 3)."""
	exercises = payload["workout"]

	date = payload.get("date")
	if not date:
		_fail("Payload has no `date`.")
	time = payload.get("time")

	sets, cardio = [], []
	for key, node in exercises.items():
		exercise = _titleize(key)
		raw_sets, equipment_path = _find_sets(node)

		if raw_sets is not None:
			equipment = " / ".join(_titleize(seg) for seg in equipment_path) or None
			if not isinstance(raw_sets, list):
				_fail("{0}: `sets` must be a list.", exercise)
			for index, raw in enumerate(raw_sets, start=1):
				if not isinstance(raw, dict):
					_fail("{0}: set {1} is not an object.", exercise, index)
				sets.append(
					_strength_row(exercise, equipment, index, raw, f"{exercise} set {index}")
				)
		elif isinstance(node, dict) and _is_cardio(node):
			# cardio names its equipment in a `type` value rather than a nested key
			cardio.append(
				_cardio_row(exercise, node.get("type") or None, node, f"{exercise} cardio")
			)
		else:
			_fail(
				"{0}: no `sets` and no `distance`/`duration` — cannot tell what this is.",
				exercise,
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


# ------------------------------------------------------------------- dispatcher

#: Wrappers seen around the real payload. `workout_log` is what shape 2 uses.
WRAPPER_KEYS = ("workout_log", "workout_session", "session", "log", "data")


def parse_workout_payload(payload):
	"""Map any supported workout export onto `Workout` + child-table field values.

	Returns a dict ready to hand to `frappe.get_doc`. Raises `WorkoutParseError` on
	anything it cannot read, rather than importing it wrongly.
	"""
	if isinstance(payload, str):
		text = payload.strip()
		if not text:
			_fail("Payload is empty.")
		if text[0] in "{[":
			try:
				payload = json.loads(text)
			except json.JSONDecodeError as exc:
				_fail("Payload is not valid JSON: {0}.", exc)
		else:
			return _parse_share_text(text)

	if not isinstance(payload, dict):
		_fail("Payload must be a JSON object or the app's share text.")

	# unwrap `{"workout_log": {...}}` and friends
	for wrapper in WRAPPER_KEYS:
		inner = payload.get(wrapper)
		if isinstance(inner, dict):
			payload = inner
			break

	if isinstance(payload.get("exercises"), list):
		if not payload["exercises"]:
			_fail("`exercises` is empty.")
		return _parse_exercise_list(payload)

	if isinstance(payload.get("workout"), dict):
		if not payload["workout"]:
			_fail("`workout` is empty.")
		return _parse_nested(payload)

	_fail(
		"Unrecognised payload. Expected an `exercises` list, a `workout` object, "
		"or the app's share text. Found keys: {0}.",
		", ".join(sorted(payload)) or "none",
	)


#: Kept so older callers and docs keep working.
parse_workout_json = parse_workout_payload


def create_workout_from_json(payload):
	"""Parse a payload and insert the resulting `Workout`. Returns the document."""
	return frappe.get_doc(parse_workout_payload(payload)).insert()


@frappe.whitelist()
def parse_payload(payload: str) -> dict:
	"""Parse a pasted payload and return `Workout` field values for the form to fill.

	Read-only — nothing is written here. The form saves normally, so the usual
	permission checks apply at save time. Parse failures surface as the
	`WorkoutParseError` message rather than a silently half-filled form.
	"""
	values = parse_workout_payload(payload)
	values.pop("doctype", None)
	return values
