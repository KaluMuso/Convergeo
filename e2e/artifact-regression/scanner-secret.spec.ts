import {
  expect,
  SCANNER_ARTIFACT_POLICY,
  test,
} from "../fixtures/scanner-artifact-test";

test.use(SCANNER_ARTIFACT_POLICY);

test("scanner secret cannot enter retained artifacts", async ({ page }) => {
  const sentinel = process.env.SCANNER_ARTIFACT_SENTINEL;
  expect(sentinel, "SCANNER_ARTIFACT_SENTINEL must be set by the regression runner").toBeTruthy();

  await page.setContent(`
    <form data-testid="event-scan-manual-fallback">
      <input data-testid="event-scan-manual-pin" type="password" />
    </form>
  `);
  await page.getByTestId("event-scan-manual-pin").fill(sentinel!);

  // Deliberate failure: the outer runner requires a failed attempt and retry,
  // then proves neither diagnostics tree contains the entered credential.
  await expect(page.getByTestId("deliberate-scanner-artifact-failure")).toBeVisible();
});
