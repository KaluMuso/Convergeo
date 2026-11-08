"use client";

/**
 * Vergeo5 toast system — the single toast implementation for all three apps.
 *
 * - Two live regions: `polite` (role=status) for success/info, `assertive`
 *   (role=alert) for errors, so screen readers interrupt only for failures.
 * - Auto-dismiss after ~4 s; the timer pauses while the toast is hovered or
 *   holds keyboard focus, and resumes on leave/blur.
 * - Swipe (pointer drag) horizontally to dismiss on touch; Escape dismisses
 *   the focused toast; every toast has a labelled close button.
 * - At most 3 visible (oldest evicted first).
 * - `notify.*` / `emitToast` raise toasts from non-React code.
 * - Motion lives in base.css (`.v-toast*`) and collapses to opacity-only under
 *   prefers-reduced-motion. Styles are plain CSS classes (packages/ui is not
 *   scanned by app Tailwind builds, so no utility classes are used here).
 */

import {
  createContext,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

export type ToastType = "success" | "error" | "info" | "cart";

export type ToastItem = {
  id: string;
  message: string;
  description?: string;
  type: ToastType;
  durationMs: number;
};

export type ToastOptions = {
  type?: ToastType;
  /** Optional second line (e.g. "View cart" context). */
  description?: string;
  durationMs?: number;
};

type ToastFn = (message: string, options?: ToastOptions) => void;

type ToastContextValue = {
  toast: ToastFn;
  success: (message: string, options?: Omit<ToastOptions, "type">) => void;
  error: (message: string, options?: Omit<ToastOptions, "type">) => void;
  info: (message: string, options?: Omit<ToastOptions, "type">) => void;
  dismiss: (id: string) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

/* ── Imperative bridge ──────────────────────────────────────────────────────
   Lets non-hook code (async cart helpers, dynamically imported modules) raise
   a toast without threading context through. The mounted provider subscribes;
   with no provider mounted, calls are dropped silently. */
type ToastListener = (message: string, options?: ToastOptions) => void;
type ToastKeyListener = (
  key: string,
  options?: ToastOptions & { values?: Record<string, string | number> },
) => void;
const toastListeners = new Set<ToastListener>();
const toastKeyListeners = new Set<ToastKeyListener>();

export function emitToast(message: string, options?: ToastOptions): void {
  for (const listener of toastListeners) {
    listener(message, options);
  }
}

/**
 * Raise a toast by copy key. The provider resolves it against its `copy` map
 * (translated server-side, e.g. `common.toast`), so call sites need no i18n
 * hook. `{name}`-style placeholders are filled from `values`. Unknown keys and
 * calls with no provider mounted are dropped silently.
 */
export function emitToastKey(
  key: string,
  options?: ToastOptions & { values?: Record<string, string | number> },
): void {
  for (const listener of toastKeyListeners) {
    listener(key, options);
  }
}

function fillTemplate(template: string, values?: Record<string, string | number>): string {
  if (!values) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}

export const notify = {
  success: (message: string, options?: Omit<ToastOptions, "type">) =>
    emitToast(message, { ...options, type: "success" }),
  error: (message: string, options?: Omit<ToastOptions, "type">) =>
    emitToast(message, { ...options, type: "error" }),
  info: (message: string, options?: Omit<ToastOptions, "type">) =>
    emitToast(message, { ...options, type: "info" }),
  cart: (message: string, options?: Omit<ToastOptions, "type">) =>
    emitToast(message, { ...options, type: "cart" }),
};

const MAX_TOASTS = 3;
const DEFAULT_DURATION_MS = 4000;
/** Errors linger a little longer so they can be read. */
const ERROR_DURATION_MS = 6000;
const EXIT_MS = 180;
const SWIPE_DISMISS_PX = 64;

let toastCounter = 0;

function nextToastId(): string {
  toastCounter += 1;
  return `toast-${toastCounter}`;
}

type ToastProviderProps = {
  children: ReactNode;
  maxToasts?: number;
  /** Accessible label for each toast's close button (pass a translated string). */
  dismissLabel?: string;
  /** Translated copy for `emitToastKey(key)` (e.g. `t.raw("toast")`). */
  copy?: Record<string, unknown>;
};

export function ToastProvider({
  children,
  maxToasts = MAX_TOASTS,
  dismissLabel = "Dismiss",
  copy,
}: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback<ToastFn>(
    (message, options) => {
      const type = options?.type ?? "info";
      const item: ToastItem = {
        id: nextToastId(),
        message,
        description: options?.description,
        type,
        durationMs:
          options?.durationMs ?? (type === "error" ? ERROR_DURATION_MS : DEFAULT_DURATION_MS),
      };
      setToasts((prev) => {
        const next = [...prev, item];
        return next.length > maxToasts ? next.slice(next.length - maxToasts) : next;
      });
    },
    [maxToasts],
  );

  useEffect(() => {
    const onKey: ToastKeyListener = (key, options) => {
      const template = copy?.[key];
      if (typeof template !== "string") {
        return;
      }
      const { values, ...rest } = options ?? {};
      const description =
        rest.description && typeof copy?.[rest.description] === "string"
          ? fillTemplate(copy[rest.description] as string, values)
          : rest.description;
      toast(fillTemplate(template, values), { ...rest, description });
    };
    toastListeners.add(toast);
    toastKeyListeners.add(onKey);
    return () => {
      toastListeners.delete(toast);
      toastKeyListeners.delete(onKey);
    };
  }, [toast, copy]);

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      success: (message, options) => toast(message, { ...options, type: "success" }),
      error: (message, options) => toast(message, { ...options, type: "error" }),
      info: (message, options) => toast(message, { ...options, type: "info" }),
      dismiss,
    }),
    [toast, dismiss],
  );

  const polite = toasts.filter((t) => t.type !== "error");
  const assertive = toasts.filter((t) => t.type === "error");

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted &&
        createPortal(
          <div className="v-toaster" data-testid="toast-viewport">
            <div
              aria-live="assertive"
              aria-relevant="additions"
              className="v-toaster__region"
              data-testid="toast-alert-region"
            >
              {assertive.map((item) => (
                <ToastView
                  key={item.id}
                  item={item}
                  onDismiss={dismiss}
                  dismissLabel={dismissLabel}
                />
              ))}
            </div>
            <div
              aria-live="polite"
              aria-relevant="additions"
              className="v-toaster__region"
              data-testid="toast-live-region"
            >
              {polite.map((item) => (
                <ToastView
                  key={item.id}
                  item={item}
                  onDismiss={dismiss}
                  dismissLabel={dismissLabel}
                />
              ))}
            </div>
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}

const noop = () => undefined;
const NOOP_CONTEXT: ToastContextValue = {
  toast: noop,
  success: noop,
  error: noop,
  info: noop,
  dismiss: noop,
};

/**
 * Same API as `useToast`, but a silent no-op outside a provider. Use in shared
 * components that may render in isolation (tests, storybook-like dev routes).
 */
export function useOptionalToast(): ToastContextValue {
  return useContext(ToastContext) ?? NOOP_CONTEXT;
}

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

function ToastView({ item, onDismiss, dismissLabel }: ToastViewProps) {
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

/** Test helper — max queue size constant. */
export const TOAST_MAX_QUEUE = MAX_TOASTS;
export const TOAST_DEFAULT_DURATION_MS = DEFAULT_DURATION_MS;
export const TOAST_ERROR_DURATION_MS = ERROR_DURATION_MS;
