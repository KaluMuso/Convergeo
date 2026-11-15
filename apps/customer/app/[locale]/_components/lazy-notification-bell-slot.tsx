"use client";

import dynamic from "next/dynamic";

/**
 * Keep the bell (poller, dropdown, toast hook) off every shop/account route's
 * first-load JS. The bell renders nothing until the client knows the unseen
 * count, so skipping SSR adds no layout shift.
 */
export const LazyNotificationBellSlot = dynamic(
  () => import("./notification-bell-slot").then((mod) => mod.NotificationBellSlot),
  { ssr: false },
);
