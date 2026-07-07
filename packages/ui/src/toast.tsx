"use client";

import {
  createContext,
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
  type: ToastType;
  durationMs: number;
};

export type ToastOptions = {
  type?: ToastType;
  durationMs?: number;
};

type ToastContextValue = {
  toast: (message: string, options?: ToastOptions) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const MAX_TOASTS = 4;
const DEFAULT_DURATION_MS = 2800;

let toastCounter = 0;

function nextToastId(): string {
  toastCounter += 1;
  return `toast-${toastCounter}`;
}

const typeColors: Record<ToastType, { bg: string; border: string; icon: string }> = {
  success: {
    bg: "color-mix(in srgb, var(--success) 12%, var(--surface))",
    border: "color-mix(in srgb, var(--success) 35%, transparent)",
    icon: "var(--success)",
  },
  error: {
    bg: "color-mix(in srgb, var(--danger) 12%, var(--surface))",
    border: "color-mix(in srgb, var(--danger) 35%, transparent)",
    icon: "var(--danger)",
  },
  info: {
    bg: "color-mix(in srgb, var(--info) 12%, var(--surface))",
    border: "color-mix(in srgb, var(--info) 35%, transparent)",
    icon: "var(--info)",
  },
  cart: {
    bg: "color-mix(in srgb, var(--accent) 12%, var(--surface))",
    border: "color-mix(in srgb, var(--accent) 35%, transparent)",
    icon: "var(--accent)",
  },
};

const typeIcons: Record<ToastType, string> = {
  success: "✓",
  error: "!",
  info: "i",
  cart: "🛒",
};

type ToastProviderProps = {
  children: ReactNode;
  maxToasts?: number;
};

export function ToastProvider({ children, maxToasts = MAX_TOASTS }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, options?: ToastOptions) => {
      const item: ToastItem = {
        id: nextToastId(),
        message,
        type: options?.type ?? "info",
        durationMs: options?.durationMs ?? DEFAULT_DURATION_MS,
      };
      setToasts((prev) => {
        const next = [...prev, item];
        if (next.length > maxToasts) {
          return next.slice(next.length - maxToasts);
        }
        return next;
      });
    },
    [maxToasts],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {mounted &&
        createPortal(
          <div
            aria-live="polite"
            aria-relevant="additions removals"
            data-testid="toast-live-region"
            style={{
              position: "fixed",
              bottom: "var(--sp-6)",
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 60,
              display: "flex",
              flexDirection: "column",
              gap: "var(--sp-2)",
              width: "min(100% - var(--sp-8), 24rem)",
              pointerEvents: "none",
            }}
          >
            {toasts.map((item) => (
              <ToastView key={item.id} item={item} onDismiss={dismiss} />
            ))}
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

type ToastViewProps = {
  item: ToastItem;
  onDismiss: (id: string) => void;
};

function ToastView({ item, onDismiss }: ToastViewProps) {
  const [exiting, setExiting] = useState(false);
  const [paused, setPaused] = useState(false);
  const remainingRef = useRef(item.durationMs);
  const timerStartRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleDismiss = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    timerStartRef.current = Date.now();
    timerRef.current = setTimeout(() => {
      setExiting(true);
      setTimeout(() => onDismiss(item.id), 200);
    }, remainingRef.current);
  }, [item.id, onDismiss]);

  useEffect(() => {
    scheduleDismiss();
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [scheduleDismiss]);

  const handleMouseEnter = () => {
    if (paused) {
      return;
    }
    setPaused(true);
    if (timerRef.current && timerStartRef.current !== null) {
      clearTimeout(timerRef.current);
      const elapsed = Date.now() - timerStartRef.current;
      remainingRef.current = Math.max(0, remainingRef.current - elapsed);
    }
  };

  const handleMouseLeave = () => {
    if (!paused) {
      return;
    }
    setPaused(false);
    scheduleDismiss();
  };

  const colors = typeColors[item.type];

  return (
    <div
      role="status"
      data-testid={`toast-${item.id}`}
      data-toast-type={item.type}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--sp-3)",
        padding: "var(--sp-3) var(--sp-4)",
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        borderRadius: "var(--r)",
        boxShadow: "var(--shadow-2)",
        color: "var(--text)",
        fontSize: "var(--fs-body)",
        pointerEvents: "auto",
        minHeight: "2.75rem",
        animation: exiting
          ? "toast-out var(--dur-fast) var(--ease-std) forwards"
          : "toast-in var(--dur) var(--ease-out)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          color: colors.icon,
          fontWeight: 700,
          width: "1.25rem",
          textAlign: "center",
          flexShrink: 0,
        }}
      >
        {typeIcons[item.type]}
      </span>
      <span style={{ flex: 1 }}>{item.message}</span>
    </div>
  );
}

/** Test helper — max queue size constant. */
export const TOAST_MAX_QUEUE = MAX_TOASTS;
export const TOAST_DEFAULT_DURATION_MS = DEFAULT_DURATION_MS;
