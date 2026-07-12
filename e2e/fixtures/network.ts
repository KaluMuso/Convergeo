import type { CDPSession } from "@playwright/test";

/**
 * Chrome DevTools "Fast 3G" network profile (the profile our LCP budget of
 * ≤2.5s @ 360px is measured against). Values match the DevTools preset:
 *   download 1.6 Mbit/s, upload 750 kbit/s, latency 150ms.
 */
export const FAST_3G = {
  offline: false,
  downloadThroughput: (1.6 * 1024 * 1024) / 8,
  uploadThroughput: (750 * 1024) / 8,
  latency: 150,
} as const;

/** Apply Fast-3G throttling to an open CDP session (Chromium only). */
export async function applyFast3G(client: CDPSession): Promise<void> {
  await client.send("Network.enable");
  await client.send("Network.emulateNetworkConditions", FAST_3G);
}
