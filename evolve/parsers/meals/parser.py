# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""Turn a check-in's free-text `meals` into `Daily Checkin Meal` rows, using Sarvam.

Text in, rows out — nothing is written here. The nightly job in `tasks.py` decides
which check-ins to parse and saves the result.

    parse_meals("poha and chai at 8, dal chawal for lunch, samosa at 5", "2026-10-11")
    -> [{"meal": "Breakfast", "item": "poha, chai", "has_caffeine": True, ...},
        {"meal": "Lunch", "item": "dal chawal", "has_protein": True, "has_fibre": True, ...},
        {"meal": "Afternoon Snack", "item": "samosa", "is_fried": True, ...}]

The allowed meal slots are read from the `meal` Select on `Daily Checkin Meal`, so
the prompt and the schema follow that field when its options change.

Each row also carries the yes/no tags in `TAGS`. The prompt and the schema are both
built from that one dict, so a tag's definition can't drift from what's asked for.

The model tags each food on its own ("mango pickle": spicy?) rather than a whole meal
("dal chawal, aloo sabzi, mango pickle": spicy?), which it got wrong when asked the
second way. The foods are then joined into one row per slot here, and a tag is true for
the row if it's true for any of its foods.

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
- One entry per slot that has food in it. List each food or drink in that slot
  separately in `foods`.
- Keep the person's own words for dishes, including Hindi, Marathi, Kannada or Hinglish names
  (e.g. "poha", "dal chawal", "sabudana khichdi"). Do not translate them but you can fix typos if any.
- Keep quantities in the food's name if given (e.g. "2 rotis", "1 bowl dal").
- Include every food and drink the log mentions. Leaving one out is as wrong as
  inventing one.
- Drinks count: tea, coffee, juice, shakes go in the slot they were had in.
- Use times and words like "morning", "after gym", "evening" to pick the slot.
  Anything first thing before breakfast is Pre-Breakfast. Snacks between lunch and dinner
  are Afternoon Snack. Use Brunch only if the log says brunch, or a single late-morning
  meal replaced both breakfast and lunch.
- Something had "after" or "with" a meal belongs to that meal's slot: a sweet after
  dinner is Dinner, not a snack.
- Each food from the log goes in exactly one slot. Never copy an item into a second slot.
- Never invent food or meals that are not in the log. Leave out slots with nothing in them.
- If the log mentions no food at all, return an empty list.

Tags: every food gets these true/false tags, judged for that food alone.
{tags}

Judge each food by how it is usually made at home in India, unless the log says otherwise
(e.g. "less oil", "decaf", "extra spicy"). If you still can't tell, use false.
"""

#: Yes/no tags on each meal row: `Daily Checkin Meal` Check field -> what counts.
#: Each definition says what's in and what's out, so the model doesn't have to guess
#: where the line is. Field names here must match the Check fields on the doctype.
TAGS = {
	"has_protein": (
		"A meaningful protein source: eggs, chicken, meat, fish, paneer, tofu, dal or other "
		"legumes (rajma, chole, sprouts), curd or yogurt, milk-based shakes, whey or protein "
		"powder, a serving of nuts or peanut butter. A splash of milk in tea does not count."
	),
	"has_fibre": (
		"Vegetables (sabzi, salad), fruit, legumes (dal, rajma, chole, sprouts), or whole "
		"grains (whole-wheat roti, oats, brown rice, millets like jowar, bajra, ragi). White "
		"rice, maida, white bread and biscuits do not count on their own."
	),
	"is_spicy": (
		"Noticeably hot from chilli or masala: e.g. misal, vada pav, biryani, chilli chicken, "
		"Schezwan dishes, spicy chutney, pickle. Mildly seasoned everyday food (plain dal, "
		"poha, roti-sabzi) does not count unless the log says it was spicy."
	),
	"is_fried": (
		"Deep- or shallow-fried: samosa, pakora or bhaji, vada, puri, bhatura, fries, chips, "
		"fried chicken. Food cooked on a pan with a little oil (roti, dosa, omelette) and "
		"tadka or tempering do not count."
	),
	"has_caffeine": (
		"Tea (chai, black, green), coffee, cola, energy drinks, chocolate drinks, dark "
		"chocolate. Herbal teas without tea leaves (chamomile, kadha) do not count."
	),
}


class MealParseError(frappe.ValidationError):
	pass


def _fail(msg, *args):
	frappe.throw(_(msg).format(*args), exc=MealParseError, title=_("Meal Parse Error"))


def meal_slots() -> list[str]:
	"""The `meal` Select options on `Daily Checkin Meal`, in their order."""
	options = frappe.get_meta("Daily Checkin Meal").get_field("meal").options or ""
	return [slot for slot in options.split("\n") if slot.strip()]


def _response_schema(slots):
	food = {
		"type": "object",
		"properties": {
			"name": {"type": "string"},
			# after `name`, so the model has written the food down before tagging it
			**{tag: {"type": "boolean"} for tag in TAGS},
		},
		"required": ["name", *TAGS],
		"additionalProperties": False,
	}
	return {
		"type": "object",
		"properties": {
			"meals": {
				"type": "array",
				"items": {
					"type": "object",
					"properties": {
						"meal": {"type": "string", "enum": slots},
						"foods": {"type": "array", "items": food},
					},
					"required": ["meal", "foods"],
					"additionalProperties": False,
				},
			}
		},
		"required": ["meals"],
		"additionalProperties": False,
	}


def _system_prompt(slots):
	tags = "\n".join(f"- {tag}: {definition}" for tag, definition in TAGS.items())
	return SYSTEM_PROMPT.format(slots=", ".join(slots), tags=tags)


def _call_sarvam(text, date, slots):
	"""POST the log to Sarvam and return the message content (a JSON string)."""
	api_key = frappe.conf.get("sarvam_api_key")
	if not api_key:
		_fail("sarvam_api_key is not set in site config.")

	payload = {
		"model": SARVAM_MODEL,
		"messages": [
			{"role": "system", "content": _system_prompt(slots)},
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
		"max_tokens": 2048,
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
	tags = {}
	for entry in entries:
		if not isinstance(entry, dict):
			continue
		slot = by_slot.get(str(entry.get("meal") or "").strip().lower())
		if not slot or not isinstance(entry.get("foods"), list):
			# an unknown slot is dropped, not guessed at
			continue

		for food in entry["foods"]:
			name = str(food.get("name") or "").strip() if isinstance(food, dict) else ""
			if not name:
				continue
			# the prompt asks for one entry per slot; this also merges if the model split one up
			items.setdefault(slot, []).append(name)
			# true for the row if true for any of its foods; anything but a real `true`
			# (missing, "yes", 1) counts as false
			slot_tags = tags.setdefault(slot, dict.fromkeys(TAGS, False))
			for tag in TAGS:
				slot_tags[tag] = slot_tags[tag] or food.get(tag) is True

	if not items:
		_fail("No meals found in the text.")

	return [
		{"meal": slot, "item": ", ".join(items[slot]), **tags[slot]} for slot in slots if slot in items
	]


def parse_meals(text: str, date: str) -> list[dict]:
	"""Parse a free-text food log into `[{"meal": ..., "item": ..., <tags>}]`, in slot order.

	Raises `MealParseError` with a short, readable reason on any failure.
	"""
	text = (text or "").strip()
	if not text:
		_fail("There is no meals text to parse.")

	slots = meal_slots()
	return _rows_from_content(_call_sarvam(text, str(date), slots), slots)
