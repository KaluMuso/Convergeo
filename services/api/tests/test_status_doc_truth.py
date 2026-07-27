"""RC-P01: keep `docs/plan/00-status.md`'s top summary from going stale again.

The failure this guards against actually happened: the top block pinned **Master tip:** `3dbf137`
and an "API 502" live line, and both were still being read as current fact a week later, after the
tip had moved many times and M17/M18 had merged. A summary that names a fixed SHA is wrong the
moment the next commit lands, and nothing in the repo noticed.

So the rule is structural rather than semantic: **the top summary may not pin a commit SHA at all.**
SHAs belong in the dated entries and evidence packs, where they are labelled with the date they were
observed. Anything a checker cannot verify — whether a migration is applied, whether CI is green,
whether an environment variable exists — stays out of the summary and lives in the dated pack, which
is why the summary must point at one.

Read-only over docs; no application behaviour is exercised.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STATUS_DOC = _REPO_ROOT / "docs" / "plan" / "00-status.md"

_GATES_HEADING = "## Current release gates"
_HISTORY_HEADING = "## History — dated entries"

#: A backticked token that looks like a git SHA: 7–40 hex chars. The digit requirement keeps
#: ordinary hex-looking words (`accede`, `defaced`) from tripping the guard; a real SHA
#: essentially always carries one.
_SHA_IN_BACKTICKS = re.compile(r"`([0-9a-f]{7,40})`")


def _doc() -> str:
    return _STATUS_DOC.read_text(encoding="utf-8")


def _summary() -> str:
    """Everything above the release-gates heading — the block read as *current* state."""
    text = _doc()
    head, sep, _ = text.partition(_GATES_HEADING)
    assert sep, f"{_STATUS_DOC.name} is missing its '{_GATES_HEADING}' section"
    return head


def test_status_doc_exists() -> None:
    assert _STATUS_DOC.is_file(), f"missing status doc: {_STATUS_DOC}"


def test_top_summary_pins_no_commit_sha() -> None:
    """The summary must not state a fixed SHA as current fact."""
    offenders = [
        sha for sha in _SHA_IN_BACKTICKS.findall(_summary()) if any(c.isdigit() for c in sha)
    ]
    assert not offenders, (
        f"docs/plan/00-status.md's top summary pins commit SHA(s) {offenders!r}. "
        "A pinned SHA in the summary is stale on the next merge — that is exactly how the "
        "2026-07-20 header survived into 2026-07-27. Say `git rev-parse origin/master` instead, "
        "and put dated SHAs in the history entries or an evidence pack."
    )


def test_top_summary_is_dated_and_points_at_an_evidence_pack() -> None:
    summary = _summary()
    assert "**Updated:**" in summary, "top summary must carry an **Updated:** date"

    packs = re.findall(r"docs/production-readiness/(\d{4}-\d{2}-\d{2})/([\w.-]+\.md)", summary)
    assert packs, (
        "top summary must cite at least one dated evidence pack under "
        "docs/production-readiness/<date>/ — claims about deployment state need a source"
    )
    for date, name in packs:
        pack = _REPO_ROOT / "docs" / "production-readiness" / date / name
        assert pack.is_file(), f"top summary cites a missing evidence pack: {pack}"


def test_release_gates_section_enumerates_every_gate() -> None:
    text = _doc()
    gates_section = text.partition(_GATES_HEADING)[2].partition(_HISTORY_HEADING)[0]
    assert gates_section.strip(), "the release-gates section is empty"
    for gate in ("RG-1", "RG-2", "RG-3", "RG-4", "RG-5"):
        assert gate in gates_section, (
            f"{gate} is missing from the release-gates section — the five gates "
            "(deploy/migrations, M17 cost guard, M18 pilot, money/legal, backup+alerting) "
            "are reported together or not at all"
        )


def test_history_is_explicitly_labelled_as_history() -> None:
    """Chronological callouts must sit under a heading that says they are snapshots."""
    text = _doc()
    assert _HISTORY_HEADING in text, (
        "the chronological '>' callouts must sit under a heading that labels them as dated "
        "history, so a reader cannot mistake an old entry for current state"
    )
    assert text.index(_GATES_HEADING) < text.index(_HISTORY_HEADING), (
        "current state must be stated before the history section"
    )


def test_d35_binding_contract_is_restated_in_current_state() -> None:
    """M18's non-negotiables must survive every future summary rewrite."""
    current = _doc().partition(_HISTORY_HEADING)[0]
    for phrase, why in (
        ("inbound-only", "WAHA is inbound-only"),
        ("no WAHA outbound acknowledgement", "no outbound acknowledgement of any kind"),
        ("M18-P05", "M18-P05 is the only reviewed listing handoff"),
        ("waha_vendor_intake", "the canonical kill switch"),
        ("SHA-512", "the pinned WAHA raw-body HMAC algorithm"),
        ("raw body", "the HMAC is computed over the raw body"),
    ):
        assert phrase in current, (
            f"D35 contract point missing from 00-status.md's current-state section: {why} "
            f"(expected the phrase {phrase!r})"
        )
