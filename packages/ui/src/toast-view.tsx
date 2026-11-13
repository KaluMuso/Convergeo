"use client";

/**
 * Toast presentation (single toast + icon). Split out of `toast.tsx` so the
 * provider/bridge stays tiny in the first-load bundle while this markup and
 * its pointer/keyboard/timer logic load as an async chunk (see `loadToastView`).
 */

import {
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import type { ToastItem, ToastType } from "./toast";

const EXIT_MS = 180;
const SWIPE_DISMISS_PX = 64;

type ToastViewProps = {
  item: ToastItem;
  onDismiss: (id: string) => void;
  dismissLabel: string;
};

function ToastIcon({ type }: { type: ToastType }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (type === "error") {
    return (
      <svg {...common}>
        <path d="M12 8v5M12 16.5v.01" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    );
  }
  if (type === "info") {
    return (
      <svg {...common}>
        <path d="M12 11v5M12 7.5v.01" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    );
  }
  if (type === "cart") {
    return (
      <svg {...common}>
        <path d="M3 4h2l2.2 10.2a1.5 1.5 0 0 0 1.5 1.2h8.4a1.5 1.5 0 0 0 1.5-1.1L20.5 8H6.2" />
        <circle cx="9.5" cy="19.5" r="1" />
        <circle cx="17" cy="19.5" r="1" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="m7.5 12.5 3 3 6-7" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

export function ToastView({ item, onDismiss, dismissLabel }: ToastViewProps) {
  const [exiting, setExiting] = useState(false);
  const [dragX, setDragX] = useState(0);
  const remainingRef = useRef(item.durationMs);
  const timerStartRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pausedByRef = useRef<{ hover: boolean; focus: boolean; drag: boolean }>({
    hover: false,
    focus: false,
    drag: false,
  });
  const dragStartRef = useRef<number | null>(null);

  const close = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    setExiting(true);
    setTimeout(() => onDismiss(item.id), EXIT_MS);
  }, [item.id, onDismiss]);

  const start = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerStartRef.current = Date.now();
    timerRef.current = setTimeout(close, remainingRef.current);
  }, [close]);

  const pause = useCallback(() => {
    if (timerRef.current && timerStartRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
      remainingRef.current = Math.max(
        0,
        remainingRef.current - (Date.now() - timerStartRef.current),
      );
      timerStartRef.current = null;
    }
  }, []);

  const setPaused = useCallback(
    (reason: "hover" | "focus" | "drag", value: boolean) => {
      const wasPaused = Object.values(pausedByRef.current).some(Boolean);
      pausedByRef.current[reason] = value;
      const isPaused = Object.values(pausedByRef.current).some(Boolean);
      if (!wasPaused && isPaused) {
        pause();
      } else if (wasPaused && !isPaused) {
        start();
      }
    },
    [pause, start],
  );

  useEffect(() => {
    start();
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [start]);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse") {
      return;
    }
    dragStartRef.current = event.clientX;
    setPaused("drag", true);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (dragStartRef.current === null) {
      return;
    }
    setDragX(event.clientX - dragStartRef.current);
  };

  const endDrag = () => {
    if (dragStartRef.current === null) {
      return;
    }
    dragStartRef.current = null;
    if (Math.abs(dragX) >= SWIPE_DISMISS_PX) {
      close();
      return;
    }
    setDragX(0);
    setPaused("drag", false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      close();
    }
  };

  const isError = item.type === "error";

  return (
    <div
      role={isError ? "alert" : "status"}
      className="v-toast"
      data-testid={`toast-${item.id}`}
      data-toast-type={item.type}
      data-state={exiting ? "closed" : "open"}
      data-swiping={dragX !== 0 ? "true" : undefined}
      style={
        dragX !== 0
          ? {
              transform: `translateX(${dragX}px)`,
              opacity: Math.max(0.2, 1 - Math.abs(dragX) / 200),
            }
          : undefined
      }
      onMouseEnter={() => setPaused("hover", true)}
      onMouseLeave={() => setPaused("hover", false)}
      onFocus={() => setPaused("focus", true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setPaused("focus", false);
        }
      }}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <span className="v-toast__icon">
        <ToastIcon type={item.type} />
      </span>
      <span className="v-toast__body">
        <span className="v-toast__message">{item.message}</span>
        {item.description ? <span className="v-toast__description">{item.description}</span> : null}
        {item.action ? (
          <a className="v-toast__action" href={item.action.href} data-testid="toast-action">
            {item.action.label}
          </a>
        ) : null}
      </span>
      <button
        type="button"
        className="v-toast__close"
        aria-label={dismissLabel}
        data-testid="toast-dismiss"
        onClick={close}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M6 6l12 12M18 6 6 18" />
        </svg>
      </button>
    </div>
  );
}
