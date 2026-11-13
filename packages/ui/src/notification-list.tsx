"use client";

/**
 * Notification list — rendered inside the bell dropdown (first page, "See all")
 * and as the full `/notifications` page (cursor pagination, "Load more").
 * Lazy-loaded by `notification-center.tsx`; import it directly on the page.
 */

import { useCallback, useEffect, useState, type ComponentType } from "react";

import {
  formatNotificationTime,
  notificationHref,
  type NotificationItem,
  type NotificationLabels,
  type NotificationLinkProps,
  type NotificationMessageRenderer,
  type NotificationsApi,
} from "./notification-center";

export type NotificationListProps = {
  api: NotificationsApi;
  locale: string;
  labels: NotificationLabels;
  renderMessage: NotificationMessageRenderer;
  variant: "dropdown" | "page";
  pageHref?: string;
  pageSize?: number;
  onNavigate?: (href: string) => void;
  LinkComponent?: ComponentType<NotificationLinkProps>;
  onClose?: () => void;
  /** Called after "mark all read" or a tap so the bell can resync. */
  onChanged?: () => void;
};

type LoadState = "loading" | "ready" | "error";

export function NotificationList({
  api,
  locale,
  labels,
  renderMessage,
  variant,
  pageHref,
  pageSize,
  onNavigate,
  LinkComponent,
  onClose,
  onChanged,
}: NotificationListProps) {
  const size = pageSize ?? (variant === "dropdown" ? 10 : 20);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [loadingMore, setLoadingMore] = useState(false);

  const loadFirst = useCallback(async () => {
    setState("loading");
    try {
      const page = await api.list(null, size);
      setItems(page.items);
      setCursor(page.next_cursor);
      setState("ready");
      if (variant === "page" && page.items.some((item) => !item.seen)) {
        void api.markSeen().catch(() => undefined);
      }
    } catch {
      setState("error");
    }
  }, [api, size, variant]);

  useEffect(() => {
    void loadFirst();
  }, [loadFirst]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api.list(cursor, size);
      setItems((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch {
      setState("error");
    } finally {
      setLoadingMore(false);
    }
  };

  const markAll = async () => {
    setItems((current) => current.map((item) => ({ ...item, seen: true, read: true })));
    try {
      await api.markAllRead();
    } finally {
      onChanged?.();
    }
  };

  const open = (item: NotificationItem) => {
    setItems((current) =>
      current.map((row) => (row.id === item.id ? { ...row, seen: true, read: true } : row)),
    );
    const done = item.read ? Promise.resolve() : api.markRead(item.id).catch(() => undefined);
    const href = notificationHref(locale, item.link_path);
    void done.finally(() => {
      onChanged?.();
      if (href) {
        if (onNavigate) onNavigate(href);
        else window.location.assign(href);
      }
    });
  };

  const hasUnread = items.some((item) => !item.read);
  const now = new Date();

  return (
    <div className="v-notif__list" data-variant={variant} data-testid="notification-list">
      <div className="v-notif__head">
        {variant === "dropdown" ? <h2 className="v-notif__title">{labels.title}</h2> : <span />}
        <div className="v-notif__head-actions">
          {hasUnread ? (
            <button
              type="button"
              className="v-notif__link-button"
              onClick={() => void markAll()}
              data-testid="notification-mark-all"
            >
              {labels.markAllRead}
            </button>
          ) : null}
          {variant === "dropdown" && onClose ? (
            <button
              type="button"
              className="v-notif__close"
              aria-label={labels.close}
              onClick={onClose}
            >
              <span aria-hidden>×</span>
            </button>
          ) : null}
        </div>
      </div>

      {state === "loading" ? (
        <p className="v-notif__status" role="status">
          {labels.loading}
        </p>
      ) : null}
      {state === "error" ? (
        <p className="v-notif__status" role="alert">
          {labels.loadError}{" "}
          <button type="button" className="v-notif__link-button" onClick={() => void loadFirst()}>
            {labels.retry}
          </button>
        </p>
      ) : null}
      {state === "ready" && items.length === 0 ? (
        <p className="v-notif__status">{labels.empty}</p>
      ) : null}

      {items.length > 0 ? (
        <ul className="v-notif__items">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="v-notif__item"
                data-read={item.read ? "true" : "false"}
                data-seen={item.seen ? "true" : "false"}
                data-testid="notification-item"
                onClick={() => open(item)}
              >
                {!item.read ? (
                  <span className="v-notif__dot">
                    <span className="v-notif__sr">{labels.unreadDot}</span>
                  </span>
                ) : null}
                <span className="v-notif__message">{renderMessage(item)}</span>
                <time className="v-notif__time" dateTime={item.created_at}>
                  {formatNotificationTime(item.created_at, locale, now)}
                </time>
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {variant === "page" && cursor ? (
        <div className="v-notif__foot">
          <button
            type="button"
            className="v-notif__more"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            data-testid="notification-load-more"
          >
            {loadingMore ? labels.loading : labels.loadMore}
          </button>
        </div>
      ) : null}
      {variant === "dropdown" && pageHref ? (
        <div className="v-notif__foot">
          {LinkComponent ? (
            <LinkComponent href={pageHref} className="v-notif__see-all" onClick={onClose}>
              {labels.seeAll}
            </LinkComponent>
          ) : (
            <a href={pageHref} className="v-notif__see-all" onClick={onClose}>
              {labels.seeAll}
            </a>
          )}
        </div>
      ) : null}
    </div>
  );
}
