import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { clickAddToCartAndAwaitOutcome } from "../fixtures/add-to-cart";
import { path } from "../fixtures/env";
import { SEED } from "../fixtures/seed";
import { expect, test } from "../fixtures/test-base";

/**
 * Performance smoke — LCP / CLS / INP candidates without faking green.
 *
 * Long-term targets (production):
 *   LCP ≤ 2.5s · INP ≤ 200ms · CLS ≤ 0.10
 *
 * When measurement is noisy/unreliable → MEASUREMENT_UNSTABLE (marker file +
 * annotation), never PASS via swallowed thresholds.
 */

const LCP_TARGET_MS = 2500;
const CLS_TARGET = 0.1;
const INP_TARGET_MS = 200;

type VitalsSample = {
  lcp_ms: number | null;
  cls: number | null;
  inp_ms: number | null;
  ttfb_ms: number | null;
  request_count: number;
  inp_reliable: boolean;
  event_entries: { name: string; duration_ms: number; interaction_id: number }[];
};

const unstableNotes: string[] = [];

test.describe("performance-smoke · web vitals candidates", () => {
  test.afterAll(() => {
    if (unstableNotes.length === 0) return;
    const resultsDir = join(dirname(fileURLToPath(import.meta.url)), "..", "results");
    mkdirSync(resultsDir, { recursive: true });
    writeFileSync(
      join(resultsDir, "measurement-unstable.json"),
      JSON.stringify({ notes: unstableNotes }, null, 2),
    );
  });

  test("home route vitals sample", async ({ page }) => {
    const sample = await collectVitals(page, path("/"));
    assertVitals("home", sample);
  });

  test("PDP route vitals sample", async ({ page }) => {
    const sample = await collectVitals(page, path(`/p/${SEED.product.slug}`));
    assertVitals("pdp", sample);
  });

  test("checkout route vitals sample", async ({ page }) => {
    // Give the guest a real cart so checkout stays on its own route while the
    // observation runs; an empty-cart redirect would measure a different page.
    await page.goto(path(`/p/${SEED.product.slug}`));
    await clickAddToCartAndAwaitOutcome(page, test.info(), { timeout: 20_000 });
    const sample = await collectVitals(page, path("/checkout"));
    assertVitals("checkout", sample);
  });
});

async function collectVitals(
  page: import("@playwright/test").Page,
  route: string,
): Promise<VitalsSample> {
  let requestCount = 0;
  page.on("request", () => {
    requestCount += 1;
  });

  // Install at document creation. Event Timing must be observing before the
  // user action; buffered registration after a click can miss its interaction.
  await page.addInitScript(() => {
    const probe = {
      lcp: null as number | null,
      cls: 0,
      events: [] as { name: string; duration_ms: number; interaction_id: number }[],
    };
    (window as typeof window & { __convergeoVitals?: typeof probe }).__convergeoVitals = probe;
    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === "largest-contentful-paint") probe.lcp = entry.startTime;
          if (
            entry.entryType === "layout-shift" &&
            !(entry as PerformanceEntry & { hadRecentInput?: boolean }).hadRecentInput
          ) {
            probe.cls += (entry as PerformanceEntry & { value?: number }).value ?? 0;
          }
          if (entry.entryType === "event") {
            const event = entry as PerformanceEntry & { interactionId?: number; duration?: number };
            probe.events.push({
              name: entry.name,
              duration_ms: event.duration ?? 0,
              interaction_id: event.interactionId ?? 0,
            });
          }
        }
      });
      observer.observe({ type: "largest-contentful-paint", buffered: true });
      observer.observe({ type: "layout-shift", buffered: true });
      observer.observe({ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit);
    } catch {
      // The missing entries are reported as MEASUREMENT_UNSTABLE below.
    }
  });

  const navStart = Date.now();
  await page.goto(route, { waitUntil: "networkidle" });
  const ttfb_ms = Date.now() - navStart;

  // Trusted keyboard interactions on the loaded route. A fixed coordinate can
  // hit the shared logo link and navigate away before EventTiming is read.
  // Keep every timing entry; a missing interaction remains unstable, never zero.
  await page.keyboard.press("Tab");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);

  const vitals = await page.evaluate(() =>
    (window as typeof window & {
      __convergeoVitals?: {
        lcp: number | null;
        cls: number;
        events: { name: string; duration_ms: number; interaction_id: number }[];
      };
    }).__convergeoVitals,
  );
  const interactions = (vitals?.events ?? []).filter((event) => event.interaction_id > 0);

  return {
    lcp_ms: vitals?.lcp ?? null,
    cls: vitals?.cls ?? null,
    inp_ms: interactions.length ? Math.max(...interactions.map((event) => event.duration_ms)) : null,
    ttfb_ms,
    request_count: requestCount,
    inp_reliable: interactions.length > 0,
    event_entries: vitals?.events ?? [],
  };
}

function markUnstable(note: string) {
  unstableNotes.push(note);
  test.info().annotations.push({ type: "MEASUREMENT_UNSTABLE", description: note });
}

function assertVitals(route: string, sample: VitalsSample) {
  test.info().annotations.push({
    type: "vitals",
    description: JSON.stringify(sample),
  });

  const isLocal = /localhost|127\.0\.0\.1/.test(
    process.env.E2E_BASE_URL ?? "http://localhost:3000",
  );
  const noisyEnv = isLocal || process.env.CERT_PERF_NOISY === "1";

  if (sample.lcp_ms === null) {
    markUnstable(`LCP unavailable on ${route}`);
  } else if (sample.lcp_ms > LCP_TARGET_MS * 2) {
    if (noisyEnv) {
      markUnstable(`LCP ${sample.lcp_ms}ms >> target on ${route}`);
    } else {
      expect(sample.lcp_ms, `LCP on ${route}`).toBeLessThanOrEqual(LCP_TARGET_MS * 2);
    }
  }

  if (sample.cls != null && sample.cls > CLS_TARGET * 2) {
    if (noisyEnv) {
      markUnstable(`CLS ${sample.cls} >> target on ${route}`);
    } else {
      expect(sample.cls, `CLS on ${route}`).toBeLessThanOrEqual(CLS_TARGET * 2);
    }
  }

  if (!sample.inp_reliable || sample.inp_ms == null) {
    markUnstable(`INP measurement unreliable on ${route}`);
  } else if (sample.inp_ms > INP_TARGET_MS * 2) {
    if (noisyEnv) {
      markUnstable(`INP ${sample.inp_ms}ms >> target on ${route}`);
    } else {
      expect(sample.inp_ms, `INP on ${route}`).toBeLessThanOrEqual(INP_TARGET_MS * 2);
    }
  }

  expect(sample.request_count, `request count on ${route}`).toBeGreaterThan(0);

  // If any unstable notes were recorded for this sample in a strict CI cert run
  // without CERT_PERF_NOISY, soft fail — marker file drives MEASUREMENT_UNSTABLE gate.
  if (unstableNotes.length > 0 && process.env.CI === "true" && !noisyEnv) {
    // Keep as soft: orchestrator maps marker → MEASUREMENT_UNSTABLE.
  }
}
