# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Turn a check-in's free-text `meals` into `Daily Checkin Meal` rows, using Sarvam.

Text in, rows out — nothing is written here. The nightly job in `tasks.py` decides
which check-ins to parse and saves the result.

    parse_meals("poha and chai at 8, dal chawal for lunch, samosa at 5", "2026-10-11")
    -> [{"meal": "Breakfast", "item": "poha, chai"},
        {"meal": "Lunch", "item": "dal chawal"},
        {"meal": "Afternoon Snack", "item": "samosa"}]

The allowed meal slots are read from the `meal` Select on `Daily Checkin Meal`, so
the prompt and the schema follow that field when its options change.

The model is held to a JSON schema, but the output is still validated here: anything
that doesn't fit raises `MealParseError` rather than landing as a half-right row.
"""

import json

import frappe
import requests
from frappe import _

SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-105b"
TIMEOUT_SECONDS = 60

SYSTEM_PROMPT = """\
You turn one day's free-text food log into meal entries.

Meal slots, in order through the day: {slots}.

Rules:
- One entry per slot that has food in it. Put everything eaten in that slot into `item`
  as a short comma-separated list.
- Keep the person's own words for dishes, including Hindi, Marathi, Kannada or Hinglish names
  (e.g. "poha", "dal chawal", "sabudana khichdi"). Do not translate them but you can fix typos if any.
- Keep quantities if given (e.g. "2 rotis", "1 bowl dal").
- Drinks count: tea, coffee, juice, shakes go in the slot they were had in.
- Use times and words like "morning", "after gym", "evening" to pick the slot.
  Anything first thing before breakfast is Pre-Breakfast. Snacks between lunch and dinner
  are Afternoon Snack. Use Brunch only if the log says brunch, or a single late-morning
  meal replaced both breakfast and lunch.
- Never invent food or meals that are not in the log. Leave out slots with nothing in them.
- If the log mentions no food at all, return an empty list.
"""


class MealParseError(frappe.ValidationError):
	pass


def _fail(msg, *args):
	frappe.throw(_(msg).format(*args), exc=MealParseError, title=_("Meal Parse Error"))


def meal_slots() -> list[str]:
	"""The `meal` Select options on `Daily Checkin Meal`, in their order."""
	options = frappe.get_meta("Daily Checkin Meal").get_field("meal").options or ""
	return [slot for slot in options.split("\n") if slot.strip()]


def _response_schema(slots):
	return {
		"type": "object",
		"properties": {
			"meals": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"meal": {"type": "string", "enum": slots},
						"item": {"type": "string"},
					},
					"required": ["meal", "item"],
					"additionalProperties": False,
				},
			}
		},
		"required": ["meals"],
		"additionalProperties": False,
	}


def _call_sarvam(text, date, slots):
	"""POST the log to Sarvam and return the message content (a JSON string)."""
	api_key = frappe.conf.get("sarvam_api_key")
	if not api_key:
		_fail("sarvam_api_key is not set in site config.")

	payload = {
		"model": SARVAM_MODEL,
		"messages": [
			{"role": "system", "content": SYSTEM_PROMPT.format(slots=", ".join(slots))},
			{"role": "user", "content": f"Date: {date}\n\nFood log:\n{text}"},
		],
		"response_format": {
			"type": "json_schema",
			"json_schema": {"name": "meal_entries", "schema": _response_schema(slots), "strict": True},
		},
		"temperature": 0,
		# thinking is on by default and bills against max_tokens; this is extraction,
		# not reasoning, so it is switched off
		"reasoning_effort": None,
		"max_tokens": 1024,
	}

	try:
		response = requests.post(
			SARVAM_URL,
			json=payload,
			headers={"api-subscription-key": api_key},
			timeout=TIMEOUT_SECONDS,
		)
	except requests.RequestException as e:
		_fail("Could not reach Sarvam: {0}", e.__class__.__name__)

	if not response.ok:
		try:
			detail = response.json().get("error", {}).get("message") or response.text
		except ValueError:
			detail = response.text
		_fail("Sarvam returned HTTP {0}: {1}", response.status_code, detail[:200])

	choice = (response.json().get("choices") or [{}])[0]
	if choice.get("finish_reason") == "length":
		_fail("Sarvam's reply was cut off before it finished.")

	content = (choice.get("message") or {}).get("content")
	if not content:
		_fail("Sarvam returned an empty reply.")

	return content


def _strip_fences(content):
	"""Drop ```json fences, in case the model wraps the JSON despite the schema."""
	content = content.strip()
	if content.startswith("```"):
		content = content.split("\n", 1)[1] if "\n" in content else ""
		content = content.rsplit("```", 1)[0]
	return content.strip()


def _rows_from_content(content, slots):
	"""Validate the model's JSON and return rows in slot order, one per slot."""
	try:
		data = json.loads(_strip_fences(content))
	except ValueError:
		_fail("Sarvam's reply was not valid JSON.")

	entries = data.get("meals") if isinstance(data, dict) else data
	if not isinstance(entries, list):
		_fail("Sarvam's reply had no list of meals.")

	by_slot = {slot.lower(): slot for slot in slots}
	items = {}
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		slot = by_slot.get(str(entry.get("meal") or "").strip().lower())
		item = str(entry.get("item") or "").strip()
		if not slot or not item:
			# an unknown slot or an empty item is dropped, not guessed at
			continue
		# the prompt asks for one entry per slot; merge if the model split one up
		items.setdefault(slot, []).append(item)

	if not items:
		_fail("No meals found in the text.")

	return [{"meal": slot, "item": ", ".join(items[slot])} for slot in slots if slot in items]


def parse_meals(text: str, date: str) -> list[dict]:
	"""Parse a free-text food log into `[{"meal": ..., "item": ...}]`, in slot order.

	Raises `MealParseError` with a short, readable reason on any failure.
	"""
	text = (text or "").strip()
	if not text:
		_fail("There is no meals text to parse.")

	slots = meal_slots()
	return _rows_from_content(_call_sarvam(text, str(date), slots), slots)
