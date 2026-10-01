# Convergeo Work access packet — 1 October 2026

This public GitHub directory makes the five Work prompts and code candidate accessible outside the isolated cloud workspace. Local `/workspace` paths do not transfer between ChatGPT chats. The cloud ZIP download mechanism failed; this is the GitHub retrieval route.

Implementation candidate: `f8cba729236c54200757f6f59ddf884df39a03fd`; tree `609486ac019b0230d191e200a0658359be36a944`. Base: `00863c2456390998bff51c9e8b52f4f9883b9382`. This directory is added in a later documentation commit; it does not replace the candidate identity for source review. Branch `codex/continuity-gap-repair` is deployment-disabled in all four tracked Vercel configurations. No deployment or shared migration was performed.

Read [the full prompts](Convergeo_ChatGPT_Work_Prompts.md), or use the individual task files:

1. [Coordinator](01_COORDINATOR.txt)
2. [Qualified database types](02_DATABASE_TYPES.txt)
3. [Financial review](03_FINANCIAL_REVIEW.txt)
4. [Merchant review](04_MERCHANT_REVIEW.txt)
5. [Production readiness via MCP](05_PRODUCTION_READINESS_MCP.txt)

[Download the public Work access ZIP](Convergeo_Work_Access_Pack_2026-10-01.zip). On its GitHub file page select **Download raw file**. It contains these prompts and the candidate patch; the full source is in this repository at the pinned candidate SHA. The patch is an alternative to checking out that candidate, not an additional patch to apply on top of it.

This access packet excludes original custody archives, private operational inputs, and detailed runtime evidence. Attach the original handoffs privately where a task needs them. The original 7.8 MB launch ZIP remains in the generating cloud workspace and has not been published publicly. There is no `Convergeo_ChatGPT_Work_Prompts.zip`; the full prompts file is Markdown.

Recorded local results: 804 financial fresh + 804 upgrade; seven F3; 185 curated; 3,225 RLS with one skipped PostgREST node subsequently executed separately and passed. Earlier JavaScript/build evidence is historical and source-bound. These statements do not replace independent execution or hosted qualification. Qualified 135-input types, reviewed coordinator integration, designated independent reviews, exact-SHA hosted acceptance and the concrete production application plan remain open gates.

The user aims for production launch. Use five parallel task chats, with the coordinator owning composition and publication. Collect concrete artifacts and gate status; do not infer production readiness from development tests.
