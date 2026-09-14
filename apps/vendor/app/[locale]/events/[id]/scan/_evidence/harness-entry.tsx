/**
 * Browser-side evidence harness for the organiser manual check-in surface.
 *
 * NOT part of the app: `_evidence` is a Next.js private folder, nothing imports
 * this module, and it is never routed or bundled. It exists so the 360/390px
 * keyboard, focus and error-state evidence is captured against the REAL
 * `ManualCheckIn` / `ScanResultFlash` components and the REAL compiled design
 * tokens, rather than against a hand-written copy that could drift from them.
 *
 * Driven by scripts/qa/evidence/event-scanner-mobile/run.mjs.
 *
 * Boundary, stated so the evidence is not over-read: this mounts the two
 * components inside the same wrapper markup `page.tsx` renders, but it does NOT
 * traverse the auth-gated Next route, the session, or the network client. What
 * it proves is layout, keyboard affordances and focus behaviour at 360/390px —
 * not routing or authorization, which the vendor component suite already covers.
 */
"use client";

import { NextIntlClientProvider } from "next-intl";
import { useState } from "react";
import { createRoot } from "react-dom/client";

import vendorMessages from "../../../../../../../../packages/i18n/messages/en/vendor.json";
import { ManualCheckIn } from "../_components/manual-check-in";
import { ScanResultFlash, type ScanResultState } from "../_components/scan-result-flash";

type HarnessControls = {
  setResult: (state: ScanResultState) => void;
  setSubmitting: (value: boolean) => void;
  submits: Array<{ ticketId: string; pin: string }>;
};

declare global {
  interface Window {
    __SCAN_HARNESS__?: HarnessControls;
  }
}

function Harness() {
  const [result, setResult] = useState<ScanResultState>({ kind: "idle" });
  const [submitting, setSubmitting] = useState(false);

  window.__SCAN_HARNESS__ = {
    setResult,
    setSubmitting,
    submits: window.__SCAN_HARNESS__?.submits ?? [],
  };

  return (
    // Exactly the wrapper page.tsx renders, around exactly the ScannerView root
    // div, so the widths and padding measured at 360/390 are the real ones.
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col p-4">
      <div
        data-testid="event-scan-root"
        style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}
      >
        {result.kind === "idle" ? null : (
          <ScanResultFlash state={result} onDismiss={() => setResult({ kind: "idle" })} />
        )}
        <ManualCheckIn
          disabled={false}
          isSubmitting={submitting}
          offline={false}
          onSubmit={(ticketId, pin) => {
            window.__SCAN_HARNESS__?.submits.push({ ticketId, pin });
          }}
          onUseCamera={() => {}}
        />
      </div>
    </main>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(
    <NextIntlClientProvider locale="en" messages={{ vendor: vendorMessages }}>
      <Harness />
    </NextIntlClientProvider>,
  );
}
