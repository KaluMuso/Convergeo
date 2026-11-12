// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createNotificationsApi,
  formatBadgeCount,
  formatNotificationTime,
  NotificationBell,
  notificationHref,
  shouldToastOnCountChange,
  type NotificationItem,
  type NotificationLabels,
  type NotificationsApi,
} from "./notification-center";
import { NotificationList } from "./notification-list";
import { ToastProvider } from "./toast";

const labels: NotificationLabels = {
  bell: "Notifications",
  bellUnread: (n) => `${n} unread notifications`,
  title: "Notifications",
  markAllRead: "Mark all as read",
  seeAll: "See all",
  empty: "Nothing yet",
  loading: "Loading",
  loadError: "Could not load",
  retry: "Retry",
  loadMore: "Load more",
  unreadDot: "Unread",
  view: "View",
  close: "Close",
};

function item(n: number, extra: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: `id-${n}`,
    type: "order_shipped",
    i18n_key: "notifications.inApp.order_shipped",
    params: { ref: `REF${n}` },
    link_path: `/account/orders/${n}`,
    created_at: "2026-11-13T10:00:00+00:00",
    seen: false,
    read: false,
    ...extra,
  };
}

const render$ = (i: NotificationItem) => `Order ${String(i.params.ref)} shipped`;

function fakeApi(
  counts: (number | null)[],
  items: NotificationItem[] = [item(1)],
): NotificationsApi {
  let call = 0;
  return {
    unseenCount: vi.fn(async () => counts[Math.min(call++, counts.length - 1)] ?? null),
    list: vi.fn(async () => ({ items, next_cursor: null })),
    markSeen: vi.fn(async () => undefined),
    markRead: vi.fn(async () => undefined),
    markAllRead: vi.fn(async () => undefined),
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("formatBadgeCount", () => {
  it("hides zero, shows 1–9 and caps at 9+", () => {
    expect(formatBadgeCount(0)).toBe("");
    expect(formatBadgeCount(-2)).toBe("");
    expect(formatBadgeCount(1)).toBe("1");
    expect(formatBadgeCount(9)).toBe("9");
    expect(formatBadgeCount(10)).toBe("9+");
    expect(formatBadgeCount(250)).toBe("9+");
  });
});

describe("shouldToastOnCountChange", () => {
  it("toasts only on an increase after the first observation", () => {
    expect(shouldToastOnCountChange(null, 4)).toBe(false);
    expect(shouldToastOnCountChange(2, 2)).toBe(false);
    expect(shouldToastOnCountChange(3, 1)).toBe(false);
    expect(shouldToastOnCountChange(1, 2)).toBe(true);
  });
});

describe("helpers", () => {
  it("prefixes locale and refuses protocol-relative links", () => {
    expect(notificationHref("bem", "/account/orders/1")).toBe("/bem/account/orders/1");
    expect(notificationHref("en", "//evil.example")).toBeNull();
    expect(notificationHref("en", null)).toBeNull();
  });

  it("formats relative time and falls back to a Lusaka date after a week", () => {
    const now = new Date("2026-11-13T12:00:00Z");
    expect(formatNotificationTime("2026-11-13T11:55:00Z", "en", now)).toMatch(/5 min/);
    // 23:30 UTC on 1 Nov is already 2 Nov in Lusaka (UTC+2).
    expect(formatNotificationTime("2026-11-01T23:30:00Z", "en", now)).toBe("Nov 2");
  });

  it("api adapter returns null (hide bell) on 401 and scopes every call to the audience", async () => {
    const request = vi.fn(async (path: string) => {
      if (path.includes("unseen-count")) throw Object.assign(new Error("x"), { status: 401 });
      return {} as never;
    });
    const api = createNotificationsApi(request as never, "vendor");
    await expect(api.unseenCount()).resolves.toBeNull();
    await api.markAllRead();
    expect(request).toHaveBeenLastCalledWith("/me/notifications/read-all?audience=vendor", {
      method: "POST",
    });
  });
});

describe("NotificationBell", () => {
  it("renders nothing while signed out", async () => {
    const api = fakeApi([null]);
    render(
      <NotificationBell
        api={api}
        locale="en"
        labels={labels}
        renderMessage={render$}
        pageHref="/en/n"
      />,
    );
    await waitFor(() => expect(api.unseenCount).toHaveBeenCalled());
    expect(screen.queryByTestId("notification-bell")).toBeNull();
  });

  it("shows a capped badge with an accessible unread label", async () => {
    const api = fakeApi([12]);
    render(
      <NotificationBell
        api={api}
        locale="en"
        labels={labels}
        renderMessage={render$}
        pageHref="/en/n"
      />,
    );
    const bell = await screen.findByTestId("notification-bell");
    expect(bell).toHaveAccessibleName("12 unread notifications");
    expect(screen.getByTestId("notification-badge")).toHaveTextContent("9+");
  });

  it("raises a toast for the newest notification when the count increases", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = fakeApi([1, 1, 2], [item(7)]);
    render(
      <ToastProvider>
        <NotificationBell
          api={api}
          locale="en"
          labels={labels}
          renderMessage={render$}
          pageHref="/en/n"
          intervalMs={1000}
        />
      </ToastProvider>,
    );
    await screen.findByTestId("notification-bell");
    expect(screen.queryByText("Order REF7 shipped")).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(await screen.findByText("Order REF7 shipped")).toBeInTheDocument();
    expect(screen.getByTestId("toast-action")).toHaveAttribute("href", "/en/account/orders/7");
    expect(screen.getByTestId("notification-badge")).toHaveTextContent("2");
  });

  it("opening the bell clears the badge and marks seen", async () => {
    const api = fakeApi([3]);
    render(
      <NotificationBell
        api={api}
        locale="en"
        labels={labels}
        renderMessage={render$}
        pageHref="/en/n"
      />,
    );
    fireEvent.click(await screen.findByTestId("notification-bell"));
    expect(api.markSeen).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("notification-badge")).toBeNull();
    expect(await screen.findByText("Order REF1 shipped")).toBeInTheDocument();
  });
});

describe("NotificationList", () => {
  it("mark all as read calls the API and restyles every row as read", async () => {
    const api = fakeApi([0], [item(1), item(2), item(3, { read: true, seen: true })]);
    const onChanged = vi.fn();
    render(
      <NotificationList
        api={api}
        locale="en"
        labels={labels}
        renderMessage={render$}
        variant="page"
        onChanged={onChanged}
      />,
    );
    await screen.findByText("Order REF1 shipped");
    const rows = screen.getAllByTestId("notification-item");
    expect(rows.map((r) => r.dataset.read)).toEqual(["false", "false", "true"]);
    fireEvent.click(screen.getByTestId("notification-mark-all"));
    await waitFor(() => expect(api.markAllRead).toHaveBeenCalledTimes(1));
    expect(screen.getAllByTestId("notification-item").map((r) => r.dataset.read)).toEqual([
      "true",
      "true",
      "true",
    ]);
    expect(screen.queryByTestId("notification-mark-all")).toBeNull();
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("tapping a row marks it read and navigates to its locale-prefixed link", async () => {
    const api = fakeApi([0], [item(4)]);
    const onNavigate = vi.fn();
    render(
      <NotificationList
        api={api}
        locale="fr"
        labels={labels}
        renderMessage={render$}
        variant="dropdown"
        onNavigate={onNavigate}
      />,
    );
    fireEvent.click(await screen.findByText("Order REF4 shipped"));
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith("/fr/account/orders/4"));
    expect(api.markRead).toHaveBeenCalledWith("id-4");
  });
});
