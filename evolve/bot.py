# Copyright (c) 2026, devdesh and contributors
# For license information, please see license.txt

"""B1-T3, the user background jobs act as.

Comments are the agents' operational log: a pull-not-push trail to check when something
looks wrong, not a feed. Each one says what a job did or why it failed, e.g.
`B1-T3: parsed 3 meals`, `B1-T3: parse failed — <reason>`,
`B1-T3: workout not auto-linked, no check-in for <date>`.

Jobs run as this user rather than Administrator so their edits and comments can be told
apart from yours. Jobs that save documents as it set `ignore_permissions`.

You can also ask it for things: mention @B1-T3 in a comment on a check-in and it
re-parses that day's meals (`on_comment`). For it to show up in the @ dropdown, Frappe
needs it enabled, a System User, and allowed in mentions, so it carries the `Bot` role:
desk access, no doctype permissions. It has no password, so it still can't log in, and
its mention emails are off. Created by `evolve.patches.create_bot_user`, made mentionable
by `evolve.patches.make_bot_mentionable`.
"""

from contextlib import contextmanager

import frappe
from frappe.desk.notifications import extract_mentions
from frappe.utils import strip_html

BOT_USER = "bots+bite@deshpande.page"
BOT_NAME = "B1-T3"
BOT_ROLE = "Bot"

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


def mentions_bot(html: str) -> bool:
	"""Whether a comment's HTML mentions B1-T3.

	A real @mention carries the user's email in `data-id`. Plain typed "@B1-T3" counts
	too, in case the mention dropdown wasn't used.
	"""
	if not html:
		return False
	return BOT_USER in extract_mentions(html) or f"@{BOT_NAME}".lower() in strip_html(html).lower()


def on_comment(comment, method=None):
	"""`Comment.after_insert`: act on @B1-T3 mentions.

	For now there is one request: on a check-in, re-parse its meals. The work is queued,
	not done here, so posting the comment doesn't wait on Sarvam. The reply comes back
	as a B1-T3 comment on the same check-in.
	"""
	if comment.comment_type != "Comment" or comment.reference_doctype != "Daily Checkin":
		return
	# B1-T3's own comments start with its name; never let it trigger itself
	if comment.comment_email == BOT_USER or not mentions_bot(comment.content):
		return

	frappe.enqueue(
		"evolve.parsers.meals.tasks.reparse_on_request",
		checkin=comment.reference_name,
		# two quick mentions run one re-parse, not two
		job_id=f"reparse_meals::{comment.reference_name}",
		deduplicate=True,
		enqueue_after_commit=True,
	)
