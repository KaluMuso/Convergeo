import type { Page } from "@playwright/test";

import { lenco as lencoEnv, lencoSandboxReady } from "./env";

/**
 * Encode an order-scoped Lenco reference in our contract charset
 * (`[-._A-Za-z0-9]`, prefix `ord-`). References are deterministic per run-input
 * but unique per call so sandbox charges never collide.
 */
export function orderReference(seedSuffix?: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  const suffix = (seedSuffix ?? rand).replace(/[^-._A-Za-z0-9]/g, "");
  return `ord-e2e-${Date.now()}-${suffix}`;
}

/** Whether the live Lenco sandbox pay leg should run this session (F9b gate). */
export function sandboxEnabled(): boolean {
  return lencoSandboxReady();
}

/**
 * Drive the Lenco MoMo sandbox charge to approval.
 *
 * MoMo is a direct USSD-push: after the app initiates the charge the customer
 * approves on-device. In sandbox, Lenco auto-approves a designated test number,
 * so here we simply wait for the app's own success surface to settle after the
 * push is accepted. This is only invoked when `sandboxEnabled()` is true — the
 * caller must skip/annotate otherwise.
 */
export async function completeSandboxMomoPush(page: Page): Promise<void> {
  if (!sandboxEnabled()) {
    throw new Error("completeSandboxMomoPush called without sandbox creds");
  }
  // The USSD wait surface is shown while Lenco pushes to the (sandbox) handset.
  await page
    .getByTestId("ussd-wait")
    .waitFor({ state: "visible", timeout: 30_000 })
    .catch(() => {
      /* some flows transition straight to success — tolerate a missed wait */
    });
  // Sandbox auto-approves the designated test MSISDN; poll for confirmation.
  await page
    .getByTestId("payment-success")
    .waitFor({ state: "visible", timeout: 90_000 });
}

export const lencoConfig = lencoEnv;
