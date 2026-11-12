"use client";

/**
 * Notification center — bell + unseen badge + dropdown, shared by the customer,
 * vendor and admin apps (docs/plan/notification-center.md).
 *
 * Kept deliberately small (it ships in the customer header island):
 * - the list UI lives in `notification-list.tsx` and is lazy-loaded the first
 *   time the panel opens;
 * - the unseen count is polled only while the document is visible, and
 *   immediately on focus / visibility regain — no websockets;
 * - when the count goes UP while the app is open, the newest notification is
 *   raised through the shared toast system (`emitToast`) and the PWA app badge
 *   is updated where `navigator.setAppBadge` exists.
 *
 * Copy is passed in by the app (next-intl), so nothing user-facing is
 * hardcoded here. Styles are plain `.v-notif*` classes in base.css (token
 * variables only), like the toast.
 */

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";

import { emitToast } from "./toast";

export type NotificationAudience = "customer" | "vendor" | "admin";

export type NotificationItem = {
  id: string;
  type: string;
  i18n_key: string;
  params: Record<string, string | number>;
  link_path: string | null;
  created_at: string;
  seen: boolean;
  read: boolean;
};

export type NotificationPage = { items: NotificationItem[]; next_cursor: string | null };

/** Minimal transport the apps hand in (e.g. `createApiClient(...).request`). */
export type NotificationRequest = <T>(path: string, init?: RequestInit) => Promise<T>;

export type NotificationsApi = {
  /** `null` = signed out / unavailable — the bell renders nothing. */
  unseenCount(): Promise<number | null>;
  list(cursor?: string | null, limit?: number): Promise<NotificationPage>;
  markSeen(ids?: string[]): Promise<void>;
  markRead(id: string): Promise<void>;
  markAllRead(): Promise<void>;
};

export type NotificationLabels = {
  /** Bell name with no unread, e.g. "Notifications". */
  bell: string;
  /** ICU-resolved by the app: receives the count, e.g. "3 unread notifications". */
  bellUnread: (count: number) => string;
  title: string;
  markAllRead: string;
  seeAll: string;
  empty: string;
  loading: string;
  loadError: string;
  retry: string;
  loadMore: string;
  unreadDot: string;
  view: string;
  close: string;
};

export type NotificationMessageRenderer = (item: NotificationItem) => string;

export const POLL_INTERVAL_MS = 60_000;
export const BADGE_CAP = 9;

/** "" for nothing to show, the number up to 9, then "9+". */
export function formatBadgeCount(count: number): string {
  if (!Number.isFinite(count) || count <= 0) return "";
  return count > BADGE_CAP ? `${BADGE_CAP}+` : String(Math.floor(count));
}

/** A toast fires only for a real increase seen while the app is open. */
export function shouldToastOnCountChange(previous: number | null, next: number): boolean {
  return previous !== null && next > previous;
}

/**
 * Relative time ("5 min ago") for the last week, otherwise a short date — both
 * computed in Africa/Lusaka so a server-rendered list never disagrees with the
 * phone's clock zone.
 */
export function formatNotificationTime(
  iso: string,
  locale: string,
  now: Date = new Date(),
  timeZone = "Africa/Lusaka",
): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const seconds = Math.round((then.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  let rtf: Intl.RelativeTimeFormat;
  try {
    rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" });
  } catch {
    rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });
  }
  if (abs < 60) return rtf.format(0, "second");
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 7 * 86_400) return rtf.format(Math.round(seconds / 86_400), "day");
  try {
    return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone }).format(
      then,
    );
  } catch {
    return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", timeZone }).format(then);
  }
}

/** Locale-prefixed in-app href for a row's locale-less link path. */
export function notificationHref(locale: string, linkPath: string | null): string | null {
  if (!linkPath || !linkPath.startsWith("/") || linkPath.startsWith("//")) return null;
  return `/${locale}${linkPath === "/" ? "" : linkPath}`;
}

/** Build the API adapter over any bearer-authenticated `request` transport. */
export function createNotificationsApi(
  request: NotificationRequest,
  audience: NotificationAudience,
  isSignedIn: () => boolean | Promise<boolean> = () => true,
): NotificationsApi {
  const q = `audience=${audience}`;
  return {
    async unseenCount() {
      if (!(await isSignedIn())) return null;
      try {
        const body = await request<{ unseen: number }>(`/me/notifications/unseen-count?${q}`);
        return typeof body.unseen === "number" ? body.unseen : 0;
      } catch (error) {
        const status = (error as { status?: number }).status;
        // Signed out / wrong role: hide the bell rather than show a broken one.
        if (status === 401 || status === 403) return null;
        throw error;
      }
    },
    list(cursor, limit = 20) {
      const c = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
      return request<NotificationPage>(`/me/notifications?${q}&limit=${limit}${c}`);
    },
    async markSeen(ids) {
      await request(`/me/notifications/seen?${q}`, {
        method: "POST",
        body: JSON.stringify(ids && ids.length ? { ids } : {}),
      });
    },
    async markRead(id) {
      await request(`/me/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
    },
    async markAllRead() {
      await request(`/me/notifications/read-all?${q}`, { method: "POST" });
    },
  };
}

type BadgeNavigator = Navigator & {
  setAppBadge?: (count?: number) => Promise<void>;
  clearAppBadge?: () => Promise<void>;
};

/** Reflect the unseen count on the installed PWA icon where supported. */
export function syncAppBadge(count: number): void {
  if (typeof navigator === "undefined") return;
  const nav = navigator as BadgeNavigator;
  try {
    if (count > 0 && typeof nav.setAppBadge === "function") {
      void nav.setAppBadge(count).catch(() => undefined);
    } else if (count <= 0 && typeof nav.clearAppBadge === "function") {
      void nav.clearAppBadge().catch(() => undefined);
    }
  } catch {
    /* unsupported — the in-app badge still works */
  }
}

/**
 * Poll the unseen count while visible. Calls `onIncrease(next, previous)` when
 * it rises. Returns `null` until the first answer (and while signed out).
 */
export function useUnseenCount(
  fetchCount: () => Promise<number | null>,
  options: {
    intervalMs?: number;
    onIncrease?: (next: number, previous: number) => void;
  } = {},
): { count: number | null; setCount: (n: number) => void; refresh: () => Promise<void> } {
  const { intervalMs = POLL_INTERVAL_MS } = options;
  const [count, setCountState] = useState<number | null>(null);
  const lastRef = useRef<number | null>(null);
  const onIncreaseRef = useRef(options.onIncrease);
  onIncreaseRef.current = options.onIncrease;
  const fetchRef = useRef(fetchCount);
  fetchRef.current = fetchCount;
  const inflight = useRef(false);

  const setCount = useCallback((n: number) => {
    lastRef.current = n;
    setCountState(n);
    syncAppBadge(n);
  }, []);

  const refresh = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const next = await fetchRef.current();
      const previous = lastRef.current;
      if (next === null) {
        lastRef.current = null;
        setCountState(null);
        return;
      }
      lastRef.current = next;
      setCountState(next);
      syncAppBadge(next);
      if (shouldToastOnCountChange(previous, next) && previous !== null) {
        onIncreaseRef.current?.(next, previous);
      }
    } catch {
      /* transient (3G) — keep the last known count, retry next tick */
    } finally {
      inflight.current = false;
    }
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    let timer: ReturnType<typeof setInterval> | undefined;
    const stop = () => {
      if (timer !== undefined) clearInterval(timer);
      timer = undefined;
    };
    const start = () => {
      stop();
      timer = setInterval(() => {
        if (document.visibilityState === "visible") void refresh();
      }, intervalMs);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void refresh();
        start();
      } else {
        stop();
      }
    };
    const onFocus = () => void refresh();
    if (document.visibilityState === "visible") {
      void refresh();
      start();
    }
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
    };
  }, [intervalMs, refresh]);

  return { count, setCount, refresh };
}

export function IconBell(props: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      width={20}
      height={20}
      className={props.className}
    >
      <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

export type NotificationLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
  onClick?: () => void;
};

const LazyNotificationList = lazy(() =>
  import("./notification-list").then((m) => ({ default: m.NotificationList })),
);

export type NotificationBellProps = {
  api: NotificationsApi;
  locale: string;
  labels: NotificationLabels;
  renderMessage: NotificationMessageRenderer;
  /** Full-page route, e.g. `/en/notifications` (customer: `/en/account/notifications`). */
  pageHref: string;
  /** Client-side navigation (router.push); falls back to location.assign. */
  navigate?: (href: string) => void;
  LinkComponent?: ComponentType<NotificationLinkProps>;
  intervalMs?: number;
  className?: string;
};

export function NotificationBell({
  api,
  locale,
  labels,
  renderMessage,
  pageHref,
  navigate,
  LinkComponent,
  intervalMs,
  className,
}: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [listKey, setListKey] = useState(0);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const onIncrease = useCallback(() => {
    void api
      .list(null, 1)
      .then((page) => {
        const newest = page.items[0];
        if (!newest || newest.seen) return;
        const href = notificationHref(locale, newest.link_path) ?? pageHref;
        emitToast(renderMessage(newest), {
          type: "info",
          action: { label: labels.view, href },
        });
      })
      .catch(() => undefined);
    setListKey((k) => k + 1);
  }, [api, labels.view, locale, pageHref, renderMessage]);

  const { count, setCount } = useUnseenCount(() => api.unseenCount(), {
    intervalMs,
    onIncrease,
  });

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (count === null) return null;

  const badge = formatBadgeCount(count);
  const accessibleName = count > 0 ? labels.bellUnread(count) : labels.bell;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && count > 0) {
      // Opening the bell clears the badge (seen ≠ read: rows stay bold).
      setCount(0);
      void api.markSeen().catch(() => undefined);
    }
  };

  const go = (href: string) => {
    setOpen(false);
    if (navigate) navigate(href);
    else window.location.assign(href);
  };

  return (
    <div ref={rootRef} className={["v-notif", className].filter(Boolean).join(" ")}>
      <button
        ref={buttonRef}
        type="button"
        className="v-notif__bell"
        aria-label={accessibleName}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-haspopup="dialog"
        data-testid="notification-bell"
        onClick={toggle}
      >
        <IconBell />
        {badge ? (
          <span className="v-notif__badge" aria-hidden data-testid="notification-badge">
            {badge}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          id={panelId}
          role="dialog"
          aria-label={labels.title}
          className="v-notif__panel"
          data-testid="notification-panel"
        >
          <Suspense fallback={<p className="v-notif__status">{labels.loading}</p>}>
            <LazyNotificationList
              key={listKey}
              api={api}
              locale={locale}
              labels={labels}
              renderMessage={renderMessage}
              variant="dropdown"
              pageHref={pageHref}
              onNavigate={go}
              LinkComponent={LinkComponent}
              onClose={() => setOpen(false)}
            />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
