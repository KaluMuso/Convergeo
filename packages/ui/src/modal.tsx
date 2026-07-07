"use client";

import {
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

/**
 * Modal uses native `<dialog>` with `showModal()` when available (browser).
 * jsdom does not fully implement the dialog top layer / `showModal`, so tests
 * and SSR fall back to `open` + fixed positioning with the same a11y contract.
 */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute("disabled") && el.getAttribute("aria-hidden") !== "true",
  );
}

function supportsDialogModal(): boolean {
  if (typeof HTMLDialogElement === "undefined") {
    return false;
  }
  try {
    const dialog = document.createElement("dialog");
    return typeof dialog.showModal === "function";
  } catch {
    return false;
  }
}

let scrollLockCount = 0;
let previousBodyOverflow = "";

export function lockBodyScroll(): void {
  if (typeof document === "undefined") {
    return;
  }
  if (scrollLockCount === 0) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  scrollLockCount += 1;
}

export function unlockBodyScroll(): void {
  if (typeof document === "undefined") {
    return;
  }
  scrollLockCount = Math.max(0, scrollLockCount - 1);
  if (scrollLockCount === 0) {
    document.body.style.overflow = previousBodyOverflow;
  }
}

export function useScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) {
      return;
    }
    lockBodyScroll();
    return () => {
      unlockBodyScroll();
    };
  }, [active]);
}

export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  active: boolean,
  onEscape?: () => void,
): void {
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useLayoutEffect(() => {
    if (!active || !containerRef.current) {
      return;
    }

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const container = containerRef.current;

    const focusInitial = () => {
      const focusables = getFocusableElements(container);
      const initial = focusables[0] ?? container;
      if (initial !== document.activeElement) {
        initial.focus();
      }
    };
    focusInitial();
    const focusFrame = requestAnimationFrame(focusInitial);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && onEscapeRef.current) {
        event.preventDefault();
        event.stopPropagation();
        onEscapeRef.current();
        return;
      }

      if (event.key !== "Tab" || !container.contains(document.activeElement)) {
        return;
      }

      const elements = getFocusableElements(container);
      if (elements.length === 0) {
        event.preventDefault();
        return;
      }

      const first = elements[0]!;
      const last = elements[elements.length - 1]!;
      const activeEl = document.activeElement as HTMLElement;

      if (event.shiftKey && activeEl === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && activeEl === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", handleKeyDown, true);
      previousFocusRef.current?.focus();
    };
  }, [active, containerRef]);
}

export type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Suppress ESC dismiss when false. Default true. */
  closeOnEscape?: boolean;
  /** Suppress scrim click dismiss when false. Default true. */
  closeOnScrimClick?: boolean;
  /** Optional id for aria-labelledby; auto-generated when omitted. */
  titleId?: string;
  className?: string;
  /** Test hook for dialog surface. */
  "data-testid"?: string;
};

const scrimStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  backgroundColor: "color-mix(in srgb, var(--panel) 55%, transparent)",
  border: "none",
  padding: 0,
  margin: 0,
  maxWidth: "none",
  maxHeight: "none",
  width: "100%",
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 50,
};

const panelStyle: React.CSSProperties = {
  background: "var(--surface)",
  color: "var(--text)",
  borderRadius: "var(--r-lg)",
  boxShadow: "var(--shadow-3)",
  width: "min(100% - var(--sp-8), 28rem)",
  maxHeight: "min(90vh, 40rem)",
  overflow: "auto",
  padding: "var(--sp-6)",
  margin: "var(--sp-4)",
  animation: "fadeSlideUp var(--dur) var(--ease-out)",
};

export function Modal({
  open,
  onClose,
  title,
  children,
  closeOnEscape = true,
  closeOnScrimClick = true,
  titleId: titleIdProp,
  className,
  "data-testid": dataTestId,
}: ModalProps) {
  const autoTitleId = useId();
  const titleId = titleIdProp ?? autoTitleId;
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [mounted, setMounted] = useState(false);
  const [useNativeModal, setUseNativeModal] = useState(false);

  useEffect(() => {
    setMounted(true);
    setUseNativeModal(supportsDialogModal());
  }, []);

  useScrollLock(open && mounted);
  useFocusTrap(dialogRef, open && mounted, closeOnEscape ? onClose : undefined);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || !open || !mounted) {
      return;
    }
    if (useNativeModal) {
      if (!dialog.open) {
        dialog.showModal();
      }
    }
    return () => {
      if (useNativeModal && dialog.open) {
        dialog.close();
      }
    };
  }, [open, useNativeModal]);

  const handleScrimClick = useCallback(
    (event: React.MouseEvent<HTMLDialogElement>) => {
      if (!closeOnScrimClick) {
        return;
      }
      if (event.target === event.currentTarget) {
        onClose();
      }
    },
    [closeOnScrimClick, onClose],
  );

  if (!open || !mounted) {
    return null;
  }

  const dialogProps = {
    ref: dialogRef,
    role: "dialog" as const,
    "aria-modal": true,
    "aria-labelledby": titleId,
    onClick: handleScrimClick,
    "data-testid": dataTestId,
    className,
    style: {
      ...scrimStyle,
      ...(useNativeModal ? {} : { border: "none" }),
    },
    ...(useNativeModal ? {} : { open: true }),
  };

  return createPortal(
    <dialog {...dialogProps}>
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <h2
          id={titleId}
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--fs-h3)",
            color: "var(--display-ink)",
            margin: "0 0 var(--sp-4)",
          }}
        >
          {title}
        </h2>
        {children}
      </div>
    </dialog>,
    document.body,
  );
}
