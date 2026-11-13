import { flag, path } from "../fixtures/env";
import { resolveGate } from "../fixtures/gating";
import { expect, test } from "../fixtures/test-base";

/**
 * M17-P04 — the Clips feed on a real browser, on Fast-3G.
 *
 * The assertions here are about **bytes**, not pixels. The component tests
 * already prove the policy; what a browser adds is the only question those
 * cannot answer: *did anything actually download?* So this spec counts video
 * responses over the wire and measures the transferred total for a browsing
 * session (S1: a 10-clip default-profile session costs ≤ 5 MB).
 *
 * The whole route is behind the `clips` feature flag (F-V1), which is OFF until
 * the founder turns it on. Rather than fail on a 404, the spec skips with an
 * annotation — the same posture the Lenco-sandbox and OTP legs already use.
 */

/** S1 from the spec: a ten-clip default-profile session. */
const SESSION_BUDGET_BYTES = 5 * 1024 * 1024;

const VIDEO_PATTERN = /\.(mp4|webm|mov|m3u8)(\?|$)/i;

test.describe("clips feed", () => {
  test.beforeEach(async () => {
    if (!flag("E2E_CLIPS")) {
      test.info().annotations.push({
        type: "skip-reason",
        description:
          "Clips route is behind the `clips` feature flag (F-V1); set E2E_CLIPS=1 once it is on.",
      });
      const gate = resolveGate({
        kind: "FEATURE_DISABLED",
        journey: "clips feed",
        fixtures: ["E2E_CLIPS"],
      });
      test.skip(true, gate.reason);
    }
  });

  test("scrolling the feed fetches no video bytes", async ({ page }) => {
    const videoRequests: string[] = [];
    page.on("request", (request) => {
      if (VIDEO_PATTERN.test(request.url())) {
        videoRequests.push(request.url());
      }
    });

    await page.goto(path("/clips"));
    await page.waitForLoadState("networkidle");

    const scroller = page.getByTestId("clips-scroller");
    await expect(scroller).toBeVisible();

    // Scroll through several cards. Poster-first means this costs WebP only.
    for (let index = 0; index < 5; index += 1) {
      await scroller.evaluate((element) => element.scrollBy(0, element.clientHeight));
      await page.waitForTimeout(300);
    }

    expect(videoRequests, `unexpected video fetches: ${videoRequests.join(", ")}`).toEqual([]);
    // D-V6: never a second <video>, no matter how far the visitor scrolls.
    expect(await page.locator("video").count()).toBeLessThanOrEqual(1);
  });

  test("data saver is on by default and the size chip precedes any play", async ({ page }) => {
    await page.goto(path("/clips"));
    await page.waitForLoadState("domcontentloaded");

    await expect(page.getByTestId("clips-data-saver-toggle")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByTestId("clip-size-chip").first()).toBeVisible();
    expect(await page.locator("video").count()).toBe(0);
  });

  test("a ten-clip browsing session stays inside the 5 MB budget (S1)", async ({ page }) => {
    let transferred = 0;
    page.on("response", async (response) => {
      const length = Number(response.headers()["content-length"] ?? 0);
      if (Number.isFinite(length)) {
        transferred += length;
      }
    });

    await page.goto(path("/clips"));
    await page.waitForLoadState("networkidle");

    const scroller = page.getByTestId("clips-scroller");
    for (let index = 0; index < 10; index += 1) {
      await scroller.evaluate((element) => element.scrollBy(0, element.clientHeight));
      await page.waitForTimeout(250);
    }
    await page.waitForLoadState("networkidle");

    expect(
      transferred,
      `10-clip session transferred ${(transferred / 1024 / 1024).toFixed(2)} MB`,
    ).toBeLessThanOrEqual(SESSION_BUDGET_BYTES);
  });

  test("tapping play loads exactly one video and scrolling away releases it", async ({ page }) => {
    await page.goto(path("/clips"));
    await page.waitForLoadState("networkidle");

    await page.getByTestId("clip-play-button").first().click();
    await expect(page.locator("video")).toHaveCount(1);

    const scroller = page.getByTestId("clips-scroller");
    await scroller.evaluate((element) => element.scrollBy(0, element.clientHeight * 2));

    // Source detached, buffer released — not merely paused.
    await expect(page.locator("video")).toHaveCount(0);
  });
});
