# Grok Bot: setup and routines for Convergeo

Paste each block into Grok Bot (bot name: **King**) as a message. Grok Bot turns "do this every …" into a Routine.

## 0. Permissions (set once)

- Connect **GitHub** with **read access** to `KaluMuso/Convergeo` only. If GitHub asks, allow comments on PRs and issues, but no push, no merge and no admin.
- Connect **Slack**, limited to the `#convergeo-agents` channel.
- Do **not** connect Gmail, Drive or any production systems for this work.
- Leave approvals on, so every outbound post or comment waits for King's OK until we trust the routines.

## 1. Morning briefing (R1)

> Every day at 07:00 Africa/Lusaka, for the GitHub repo KaluMuso/Convergeo: list open pull requests with their check status (green, or the names of the failing checks), read `docs/ops/agent-board.md` on master and list rows that are `in progress` or `blocked` with no commit in 24 hours, and list anything `ready for review`. Post a short summary to Slack #convergeo-agents with PR links. Read-only: never push, merge, close, label or change anything.

## 2. Nightly handoff (R2)

> Every day at 23:00 Africa/Lusaka: post to Slack #convergeo-agents "Night handoff", with each PR opened or updated today on KaluMuso/Convergeo, its check status, and the board rows whose status changed today. End with "@Claude: review queue" followed by the PR numbers that are green and `ready for review`. Read-only.

## 3. On demand

> Check PR #<n> on KaluMuso/Convergeo: summarise what changed, list failing checks with the first error line from each failing job log, and say whether it touches `supabase/migrations`, `scripts/ci`, `.github/workflows` or payments code. Do not change anything.

## Cost

Each routine run uses the shared Grok weekly pool. Two runs a day is plenty, so don't make anything hourly.
