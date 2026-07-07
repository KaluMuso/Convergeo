"use client";

import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { getFocusableElements, useFocusTrap, useScrollLock } from "./modal";

const DISMISS_THRESHOLD_PX = 80;

export type BottomSheetProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Snap-open height as CSS value, e.g. "50vh" or "24rem". Default "auto". */
  snapHeight?: string;
  closeOnEscape?: boolean;
  closeOnScrimClick?: boolean;
  titleId?: string;
  "data-testid"?: string;
};

const scrimStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  backgroundColor: "color-mix(in srgb, var(--panel) 55%, transparent)",
  zIndex: 50,
  display: "flex",
  alignItems: "flex-end",
  justifyContent: "center",
  border: "none",
  padding: 0,
  margin: 0,
  maxWidth: "none",
  maxHeight: "none",
  width: "100%",
  height: "100%",
};

export function BottomSheet({
  open,
  onClose,
  title,
  children,
  snapHeight = "auto",
  closeOnEscape = true,
  closeOnScrimClick = true,
  titleId: titleIdProp,
  "data-testid": dataTestId,
}: BottomSheetProps) {
  const autoTitleId = useId();
  const titleId = titleIdProp ?? autoTitleId;
  const dialogRef = useRef<HTMLDialogElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const dragStartY = useRef<number | null>(null);
  const dragOffsetRef = useRef(0);
  const isDragging = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useScrollLock(open && mounted);
  useFocusTrap(dialogRef, open && mounted, closeOnEscape ? onClose : undefined);

  useEffect(() => {
    if (!open) {
      setDragOffset(0);
      dragOffsetRef.current = 0;
    }
  }, [open]);

  const handlePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    isDragging.current = true;
    dragStartY.current = event.clientY;
    dragOffsetRef.current = 0;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // jsdom may not implement pointer capture
    }
  }, []);

  const handlePointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging.current || dragStartY.current === null) {
      return;
    }
    const delta = event.clientY - dragStartY.current;
    const next = Math.max(0, delta);
    dragOffsetRef.current = next;
    setDragOffset(next);
  }, []);

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!isDragging.current) {
        return;
      }
      isDragging.current = false;
      const startY = dragStartY.current;
      dragStartY.current = null;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // jsdom may not implement pointer capture
      }

      const delta = Math.max(
        startY !== null ? Math.max(0, event.clientY - startY) : 0,
        dragOffsetRef.current,
      );
      dragOffsetRef.current = 0;
      setDragOffset(0);
      if (delta >= DISMISS_THRESHOLD_PX) {
        onClose();
      }
    },
    [onClose],
  );

  const handleScrimClick = useCallback(
    (event: React.MouseEvent<HTMLDialogElement>) => {
      if (!closeOnScrimClick) {
        return;
      }
      const target = event.target as HTMLElement;
      if (target === dialogRef.current) {
        onClose();
      }
    },
    [closeOnScrimClick, onClose],
  );

  if (!open || !mounted) {
    return null;
  }

  const sheetStyle: React.CSSProperties = {
    background: "var(--surface)",
    color: "var(--text)",
    borderRadius: "var(--r-lg) var(--r-lg) 0 0",
    boxShadow: "var(--shadow-3)",
    width: "100%",
    maxWidth: "40rem",
    maxHeight: snapHeight === "auto" ? "85vh" : snapHeight,
    height: snapHeight === "auto" ? "auto" : snapHeight,
    overflow: "auto",
    padding: "var(--sp-4) var(--sp-6) var(--sp-6)",
    transform: dragOffset > 0 ? `translateY(${dragOffset}px)` : undefined,
    transition:
      dragOffset > 0
        ? "none"
        : `transform var(--dur) var(--ease-out), opacity var(--dur) var(--ease-out)`,
    animation: dragOffset > 0 ? undefined : "fadeSlideUp var(--dur) var(--ease-out)",
    touchAction: "none",
  };

  return createPortal(
    <dialog
      ref={dialogRef}
      open
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={handleScrimClick}
      data-testid={dataTestId}
      style={scrimStyle}
      tabIndex={-1}
    >
      <div
        ref={sheetRef}
        style={sheetStyle}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        data-testid={dataTestId ? `${dataTestId}-sheet` : undefined}
      >
        <div
          role="presentation"
          style={{
            width: "2.75rem",
            height: "4px",
            background: "var(--border)",
            borderRadius: "var(--r-pill)",
            margin: "0 auto var(--sp-4)",
            cursor: "grab",
            flexShrink: 0,
            touchAction: "none",
          }}
          data-testid={dataTestId ? `${dataTestId}-handle` : undefined}
        />
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
        <div>{children}</div>
      </div>
    </dialog>,
    document.body,
  );
}

/** Exported for tests — first focusable in sheet. */
export function getSheetFocusables(sheet: HTMLElement): HTMLElement[] {
  return getFocusableElements(sheet);
}
