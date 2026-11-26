/** Shared 8-character order reference shown to sellers (matches returns, disputes, scan). */
export function formatOrderCode(orderId: string): string {
  const trimmed = orderId.trim();
  if (trimmed.length === 0) {
    return "";
  }
  return trimmed.slice(0, 8).toUpperCase();
}
