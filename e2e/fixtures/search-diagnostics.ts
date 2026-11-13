import { type Page, test } from "@playwright/test";

/**
 * Failure-time evidence for the canonical search assertion.
 *
 * Run #68 had one retry fail on `search-results-list`. Source inspection shows
 * that testid is correct and conditional: ResultsList returns null when there
 * are zero hits, which is honest UI, not a defect. So the open question is not
 * "is the selector right" but "did the canonical guaranteed search term
 * actually return zero hits" — and a bare locator timeout cannot tell us.
 *
 * This captures which honest state the page was ACTUALLY in at the moment the
 * assertion gave up, and re-throws the original error unchanged:
 *
 *   search-zero-results    -> the seeded term genuinely matched nothing. That is
 *                             a canonical seed / search-index problem and a
 *                             SEPARATE root cause, not a test-timing issue.
 *   search-results-loading -> the surface never resolved within the assertion's
 *                             own budget.
 *   search-unavailable     -> the search backend reported itself unavailable.
 *   (none of the above)    -> the page was not the search surface at all.
 *
 * Deliberately NOT a remedy: it adds no wait, no retry, no sleep, no fallback
 * selector, and does not soften the assertion. Every read here runs only after
 * the assertion has already failed and its timeout has already elapsed, so it
 * cannot change pass/fail — it only makes the failure legible.
 */
export async function captureSearchStateOnFailure<T>(
  page: Page,
  assertion: () => Promise<T>,
): Promise<T> {
  try {
    return await assertion();
  } catch (error) {
    const states = ["search-zero-results", "search-results-loading", "search-unavailable"];
    const observed: string[] = [];
    for (const state of states) {
      // Instantaneous DOM reads on an already-failed assertion — no waiting.
      const count = await page
        .getByTestId(state)
        .count()
        .catch(() => 0);
      if (count > 0) {
        observed.push(state);
      }
    }

    const resultRows = await page
      .getByTestId("search-result-row")
      .count()
      .catch(() => 0);
    const productCards = await page
      .getByTestId("search-product-card")
      .count()
      .catch(() => 0);

    test.info().annotations.push({
      type: "SEARCH_STATE_ON_FAILURE",
      description: JSON.stringify({
        url: page.url(),
        observed_states: observed.length > 0 ? observed : ["none"],
        search_result_rows: resultRows,
        search_product_cards: productCards,
        zero_hits_confirmed: observed.includes("search-zero-results"),
      }),
    });

    throw error;
  }
}
