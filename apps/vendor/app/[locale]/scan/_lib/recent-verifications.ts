export type RecentVerification = {
  orderId: string;
  verifiedAt: string;
};

const STORAGE_KEY = "vergeo5.vendor.scan.recent.v1";
const MAX_RECENT = 10;

export function readRecentVerifications(): RecentVerification[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as RecentVerification[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function appendRecentVerification(orderId: string): RecentVerification[] {
  const next: RecentVerification = {
    orderId,
    verifiedAt: new Date().toISOString(),
  };
  const existing = readRecentVerifications().filter((item) => item.orderId !== orderId);
  const merged = [next, ...existing].slice(0, MAX_RECENT);
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  }
  return merged;
}
