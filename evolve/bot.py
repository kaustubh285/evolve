# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""B1-T3, the user background jobs act as.

Comments are the agents' operational log: a pull-not-push trail to check when something
looks wrong, not a feed. Each one says what a job did or why it failed, e.g.
`B1-T3: parsed 3 meals`, `B1-T3: parse failed — <reason>`,
`B1-T3: workout not auto-linked, no check-in for <date>`.

Jobs run as this user rather than Administrator so their edits and comments can be told
apart from yours. The user has no roles and is disabled, so it can't log in; jobs that
save documents as it set `ignore_permissions`. Created by
`evolve.patches.create_bot_user`.
"""

from contextlib import contextmanager

import frappe
from frappe.utils import strip_html

BOT_USER = "bots+bite@deshpande.page"
BOT_NAME = "B1-T3"

# long reasons are cut; the full traceback is in Error Log
MAX_REASON_LENGTH = 300


@contextmanager
def acting_as_bot():
	"""Run the block as B1-T3, then switch back to whoever was running before."""
	previous = frappe.session.user
	frappe.set_user(BOT_USER)
	try:
		yield
	finally:
		frappe.set_user(previous)


def log(doc, message: str):
	"""Add a `B1-T3: <message>` comment to `doc`'s timeline.

	Always attributed to B1-T3, including when called from a request made by a person,
	e.g. a document hook running during their save.
	"""
	doc.add_comment("Comment", f"{BOT_NAME}: {message}", comment_email=BOT_USER, comment_by=BOT_NAME)


def reason(exc: Exception) -> str:
	"""A one-line, plain-text reason for a comment, from any exception."""
	text = " ".join(strip_html(str(exc)).split()) or exc.__class__.__name__
	if len(text) > MAX_REASON_LENGTH:
		text = text[: MAX_REASON_LENGTH - 1] + "…"
	return text
