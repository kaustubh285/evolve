# evolve

A self-hosted personal health, fitness, and life-tracking app built on the [Frappe Framework](https://frappeframework.com/). One backend, one place, my data.

`evolve` grew out of a migraine-ledger learning project into a single system for tracking the things that change over time — headaches, training, food, and (later) expenses — so the connections between them become queryable rather than scattered across separate apps and spreadsheets.

## Why this exists

- **One backend for personal data.** Migraine logs, gym sessions, food, and expenses live in one place, so cross-domain questions ("did spending or eating shift during high-migraine weeks?") are a query, not three manual exports.
- **Self-hosted and private.** No third-party health SaaS. My data stays on infrastructure I control.
- **Frappe proving ground.** This is also where I go deeper on Frappe than work projects allow — a non-tutorial repo to trial ideas (build-toolchain changes, AI-assisted input parsing) before proposing them to a team.

## Domains

| Domain | Status | Notes |
|---|---|---|
| Migraine / health | In progress | Migrated from the original migraine-ledger app |
| Gym / training | Planned | Sessions, exercises, load |
| Food / nutrition | Planned | Verbal/text input first; photo-based estimation as a later experiment |
| Expenses | Planned | Porting an existing Google Form + Sheets tracker |

## Stack

- **Framework:** Frappe (Python), MariaDB, Redis, background workers
- **UI:** Frappe desk + PWA for mobile form entry; custom React components where needed
- **Hosting:** Self-hosted on a Linux box, production bench (supervisor + nginx + gunicorn)
- **Access:** Reached over a private [Tailscale](https://tailscale.com/) tailnet — no public exposure

## Architecture note

In Frappe, an **app** (a Python package of code + DocTypes) is separate from a **site** (a database + config that installs apps). `evolve` is a single app installed onto its own site. Apps are installed, never folder-copied between sites.

## Local development

Assumes an existing [bench](https://frappeframework.com/docs/user/en/bench) setup.

```bash
# Get the app onto your bench
bench get-app evolve <repo-url>

# Create a site (or reuse an existing one)
bench new-site evolve.local

# Install the app onto the site
bench --site evolve.local install-app evolve

# Run in dev mode
bench start
```

Visit the site at the configured host. For mobile access over Tailscale, run in production mode (`sudo bench setup production <user>`) and reach it by the tailnet host name.

## Data migration

Existing records (e.g. migraine history) are moved via CSV export from the source, then loaded through Frappe's built-in **Data Import** into the matching DocType. Code is rewritten; data is migrated.

## Roadmap

- [ ] Rebuild core health DocTypes on the new app
- [ ] Import existing migraine data
- [ ] Gym + food domains
- [ ] Text/verbal input parsing (LLM → structured fields)
- [ ] Expense tracker port (Google Form + Sheets → Frappe)
- [ ] Cross-domain reports and scheduled analytics

## License

Personal project. Not currently licensed for reuse.
