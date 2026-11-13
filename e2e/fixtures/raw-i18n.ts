import { expect } from "@playwright/test";

import type { Page } from "@playwright/test";

/**
 * Raw-i18n detectors for the pilot journeys.
 *
 * A translated surface must never leak the machinery that produced it. The
 * recent `{distance} away` defect (PDP/compare rendering an ICU placeholder
 * with no value) is the canonical example; the same family also covers a
 * message id printed in place of a message (`checkout.card.pending`) and the
 * next-intl error codes surfaced to the browser console.
 *
 * Everything here reads RENDERED text (`innerText`) and the browser console, so
 * it is independent of locale, markup and test ids.
 */

/** `{distance}`, `{count, plural, ...}`, `{amount}` — an unsubstituted ICU argument. */
export const RAW_ICU_PLACEHOLDER = /\{\s*[A-Za-z_][A-Za-z0-9_]*\s*(?:,[^{}]*)?\}/;

/**
 * A dotted message id in place of copy: `<namespace>.<segment>.<segment>`.
 * Anchored to the real top-level namespaces so ordinary text ("e.g.", a host
 * name, a version number) cannot match.
 */
export const RAW_MESSAGE_ID =
  /\b(?:account|admin|ai|auth|catalog|checkout|clips|common|directory|events|legal|marketing|nav|notifications|orders|search|services|supplies|vendor)\.[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\b/;

/** next-intl failure codes / messages as they appear in a console error. */
export const I18N_CONSOLE_ERROR =
  /MISSING_MESSAGE|INVALID_MESSAGE|FORMATTING_ERROR|ENVIRONMENT_FALLBACK|INVALID_KEY|IntlError|Could not resolve `|Missing message/i;

export type I18nProblem = { kind: "icu-placeholder" | "message-id"; sample: string };

/** Pure scan used by the specs and by the self-check below. */
export function scanRenderedText(text: string): I18nProblem[] {
  const problems: I18nProblem[] = [];
  for (const line of text.split("\n")) {
    const icu = RAW_ICU_PLACEHOLDER.exec(line);
    if (icu) problems.push({ kind: "icu-placeholder", sample: line.trim().slice(0, 120) });
    const id = RAW_MESSAGE_ID.exec(line);
    if (id) problems.push({ kind: "message-id", sample: id[0] });
  }
  return problems;
}

/**
 * Record browser console errors that look like i18n failures. Call BEFORE
 * navigation; read `.messages` after the page has settled.
 */
export function watchI18nConsole(page: Page): { messages: string[] } {
  const state = { messages: [] as string[] };
  page.on("console", (message) => {
    if (message.type() !== "error" && message.type() !== "warning") return;
    const text = message.text();
    if (I18N_CONSOLE_ERROR.test(text)) state.messages.push(text.slice(0, 200));
  });
  page.on("pageerror", (error) => {
    if (I18N_CONSOLE_ERROR.test(error.message)) state.messages.push(error.message.slice(0, 200));
  });
  return state;
}

/**
 * Assert the rendered body carries no raw ICU argument or message id.
 * `scope` narrows the scan (default: the whole body).
 */
export async function expectNoRawI18n(page: Page, scope = "body"): Promise<void> {
  const text = await page.locator(scope).first().innerText();
  const problems = scanRenderedText(text);
  expect(
    problems,
    `raw i18n leaked into rendered text: ${JSON.stringify(problems.slice(0, 5))}`,
  ).toEqual([]);
}
