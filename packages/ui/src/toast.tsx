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
  type ComponentType,
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";

export type ToastType = "success" | "error" | "info" | "cart";

export type ToastAction = { label: string; href: string };

export type ToastItem = {
  id: string;
  message: string;
  description?: string;
  action?: ToastAction;
  type: ToastType;
  durationMs: number;
};

export type ToastOptions = {
  type?: ToastType;
  /** Optional second line (e.g. "View cart" context). */
  description?: string;
  /** Optional link rendered inside the toast (e.g. "See your feed"). */
  action?: ToastAction;
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

type ToastViewComponent = ComponentType<{
  item: ToastItem;
  onDismiss: (id: string) => void;
  dismissLabel: string;
}>;

let loadedToastView: ToastViewComponent | null = null;
let toastViewPromise: Promise<ToastViewComponent> | null = null;

/**
 * Loads the toast presentation chunk (cached). The provider calls it when idle
 * after mount, so the markup stays out of the first-load bundle yet is ready
 * before the first toast in practice. Exported for tests to await.
 */
export function loadToastView(): Promise<ToastViewComponent> {
  toastViewPromise ??= import("./toast-view").then((mod) => {
    loadedToastView = mod.ToastView;
    return mod.ToastView;
  });
  return toastViewPromise;
}

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

  const [View, setView] = useState<ToastViewComponent | null>(() => loadedToastView);

  useEffect(() => {
    setMounted(true);
    let cancelled = false;
    const load = () => {
      void loadToastView().then((component) => {
        if (!cancelled) {
          setView(() => component);
        }
      });
    };
    const idle = (
      globalThis as { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }
    ).requestIdleCallback;
    if (typeof idle === "function") {
      idle(load, { timeout: 2000 });
    } else {
      setTimeout(load, 1);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  // A toast raised before the chunk is idle-loaded should not wait for idle.
  useEffect(() => {
    if (toasts.length > 0 && !View) {
      void loadToastView().then((component) => setView(() => component));
    }
  }, [toasts.length, View]);

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
        action: options?.action,
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
              {View &&
                assertive.map((item) => (
                  <View key={item.id} item={item} onDismiss={dismiss} dismissLabel={dismissLabel} />
                ))}
            </div>
            <div
              aria-live="polite"
              aria-relevant="additions"
              className="v-toaster__region"
              data-testid="toast-live-region"
            >
              {View &&
                polite.map((item) => (
                  <View key={item.id} item={item} onDismiss={dismiss} dismissLabel={dismissLabel} />
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

/** Test helper — max queue size constant. */
export const TOAST_MAX_QUEUE = MAX_TOASTS;
export const TOAST_DEFAULT_DURATION_MS = DEFAULT_DURATION_MS;
export const TOAST_ERROR_DURATION_MS = ERROR_DURATION_MS;
