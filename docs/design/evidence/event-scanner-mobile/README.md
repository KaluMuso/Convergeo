# Organiser manual check-in — 360/390px keyboard, focus and error-state evidence

Closes the outstanding third item of the M10-P06b (#700) v3 Packet B follow-up:
the mobile keyboard, focus and error-state evidence for the organiser event
scanner's manual (PIN) check-in.

Reproduce:

```bash
pnpm i
node scripts/qa/evidence/event-scanner-mobile/run.mjs
```

It writes `evidence.json` and the screenshots in this directory, and **exits
non-zero if the operator's focus leaves the field mid-verification**, so it is a
check, not just a capture.

## What was actually exercised

Real Chromium (`/opt/pw-browsers/chromium`, via Playwright), at the two
certification mobile viewports from `e2e/fixtures/viewports.ts` — `mobile-360`
(360×800) and `mobile-390` (390×844), `isMobile`/`hasTouch`, DPR 2 — driving the
real `ManualCheckIn` and `ScanResultFlash` components, compiled through the real
Tailwind entry and design tokens, inside the same wrapper markup `page.tsx`
renders.

**Boundary, so this is not over-read:** the harness mounts those components
directly. It does **not** traverse the auth-gated Next route, the Supabase
session, or the network client — the vendor middleware requires a verified
vendor session, which cannot be forged locally without standing up Supabase.
So this evidence covers layout, keyboard affordances, focus and error rendering.
It does **not** cover routing or authorization, which the 31-test vendor
component suite and the API tests already cover.

No staging, no deployment, no check-in is ever performed: nothing shared is
touched by running this.

## Results — identical at 360px and 390px

|                                 | mobile-360                                            | mobile-390          |
| ------------------------------- | ----------------------------------------------------- | ------------------- |
| Tab order (form complete)       | ticket-id → pin → submit → camera switch              | same                |
| Tab order (form empty)          | ticket-id → pin → camera switch                       | same                |
| PIN `inputMode` / `pattern`     | `numeric` / `\d{6}`                                   | same                |
| PIN rejects non-digits          | typed `12ab34xy56789` → `123456`                      | same                |
| Enter from PIN field            | submits exactly once                                  | same                |
| Focus kept through verification | **yes** (was: lost)                                   | **yes** (was: lost) |
| Error flash                     | `role="alert"`, `data-scan-result-kind="invalid_pin"` | same                |
| Wrong PIN offers override       | no                                                    | no                  |
| Horizontal overflow             | none                                                  | none                |
| Touch targets                   | all 328×44 (≥44px)                                    | all 328×44          |
| Console errors                  | 0                                                     | 0                   |

The empty-form walk skipping the submit button is correct, not a defect: the
button is `disabled` until the form is complete, and a disabled button is not
tabbable. The complete-form walk is the order an operator actually sees.

## The one defect this found, and the fix

**An in-flight verification destroyed the operator's focus.** Both fields were
`disabled` for the duration of the request. A disabled control cannot hold
focus, so Chromium dropped focus to `<body>` — and on a phone that also closes
the on-screen keyboard, mid-check-in, with a queue waiting.

Recorded before/after, both viewports:

```
before:  submit via Enter on PIN : after=event-scan-manual-pin  inFlight=body                    focusKept=false
after:   submit via Enter on PIN : after=event-scan-manual-pin  inFlight=event-scan-manual-pin   focusKept=true
```

Fix: lock the fields with `readOnly` instead of `disabled` (plus `aria-busy`,
and the same muted chrome via `:read-only` so a locked field still reads as
locked). `readOnly` refuses the edit — which is the part that has to hold — and
keeps the focus, which does not have to be destroyed to achieve it.
`mobile-360-03-in-flight.png` shows both fields muted with the PIN field's focus
ring still on it.

Unchanged: the server-side atomic single-use claim, the synchronous
`manualBusyRef` submit lock and previous-verdict reset from #704, PIN secrecy
(still state-only, still cleared on submit), wrong-PIN and conflict handling,
offline refusal, and authorization.

### Why the regression for this lives in the harness, not in jsdom

jsdom does not implement the browser behaviour that makes this a bug: it leaves
`activeElement` on an input that has just been disabled. A focus assertion in
jsdom therefore passes against the old code _and_ the new one, so it would prove
nothing — it was written, found to be non-discriminating, and removed rather
than left in looking like proof.

What jsdom can hold is the mechanism, and that regression is real: _"locks the
fields in flight without disabling them"_ in `event-scan-manual.test.tsx` fails
against the old behaviour. The focus claim itself is asserted by `run.mjs`,
which was run against the reverted component and exited 1 at both viewports.

## Found while measuring — reported, not fixed

1. **Tapping the submit button still loses focus** (`focusKept=false`, recorded
   above alongside the Enter path so this is not cherry-picked). Activating it
   clears the single-use PIN, which makes the form incomplete, so the shared
   `packages/ui` `Button` disables itself on the same tick and focus goes with
   it. Not fixed here: the cause is in `packages/ui`, outside this packet's file
   ownership, and the alternative — force-moving focus into a field — would pop
   the on-screen keyboard unbidden on a phone. Needs a call on which is wanted.

2. **Opening the manual form loses focus.** Tapping "Enter ticket PIN instead"
   unmounts that button, so focus falls to `<body>`; reproduced in the component
   suite, not in this harness (the harness mounts the form directly). Repairing
   focus the switch destroyed is unambiguous; auto-focusing when the form opens
   _by itself_ on camera denial is not, because it would jump a screen-reader
   operator past the "camera unavailable" explanation. Left for a decision
   rather than guessed at.

3. **`RecentScans` duplicate React key.** Rows are keyed
   `` `${ticketId}-${scannedAt}` ``; two entries for one ticket at one timestamp
   collide and React warns. Surfaced once the test's `next-intl` mock stopped
   remounting the tree (below). Harmless in the suite, but the offline queue can
   sync an entry the manual path already recorded.

4. **The ticket ID is visually truncated at 360px** (`mobile-360-01-idle.png`).
   The field scrolls and nothing overflows the viewport, so this is a
   legibility question, not a layout break: an operator cannot see a whole UUID
   at once to compare it against a printed ticket.

## A test-harness defect fixed along the way

The suite's `next-intl` mock returned a **new** `t` function on every render.
Real next-intl memoises it (`use-intl`'s `useTranslationsImpl` wraps it in
`useMemo`), so `t` is referentially stable. `t` is in the dependency list of
`ScannerView`'s event-load effect, so the mock made that effect re-run on every
render, flip `loadingEvent` back to true, and **silently unmount the whole
scanner** — the form the operator is typing in included — behind the spinner.

That is an artefact of the mock and does not happen in the app, but while it
stood, nothing about focus or retained field state was testable. The mock now
matches next-intl. All 203 vendor tests pass, and the scanner suite runs in
~4.5s instead of ~20s because the tree no longer remounts continuously.

## Deliberately not repeated

Readiness/settle, seeded-instance identity, and conflict/no-override behaviour
(#700), and the previous-success persistence and same-tick reentry work (#704),
were verified as already landed on staging and left alone.
