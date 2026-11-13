"use client";

import { useSyncExternalStore, type ReactNode } from "react";

import type { CartResponse, ChangeNotice, MiniCartLabels } from "./mini-cart-drawer";

type CartStoreState = {
  cart: CartResponse | null;
  notices: ChangeNotice[];
  loading: boolean;
  /** True when the last cart refresh failed (distinct from an empty cart). */
  loadError: boolean;
  drawerOpen: boolean;
  lastAddedMessage: string | null;
};

type CartStoreListener = () => void;

let storeState: CartStoreState = {
  cart: null,
  notices: [],
  // Start loading so the cart page does not flash an empty state before the
  // first refresh completes (empty vs load-error must stay distinct).
  loading: true,
  loadError: false,
  drawerOpen: false,
  lastAddedMessage: null,
};

const storeListeners = new Set<CartStoreListener>();

function emitStore() {
  storeListeners.forEach((listener) => listener());
}

export function setStoreState(patch: Partial<CartStoreState>) {
  storeState = { ...storeState, ...patch };
  emitStore();
}

/** Test-only store reset/patch — not for production UI. */
export function setStoreStateForTests(patch: Partial<CartStoreState>) {
  setStoreState(patch);
}

export function subscribeStore(listener: CartStoreListener): () => void {
  storeListeners.add(listener);
  return () => storeListeners.delete(listener);
}

function getStoreSnapshot(): CartStoreState {
  return storeState;
}

export function getCartItemCount(cart: CartResponse | null): number {
  if (!cart) {
    return 0;
  }
  // Quantities can represent incompatible measures (for example kg and metres),
  // so the cart badge counts distinct lines instead of adding unlike units.
  return cart.items.length;
}

export function openMiniCart() {
  setStoreState({ drawerOpen: true });
}

export function closeMiniCart() {
  setStoreState({ drawerOpen: false });
}

export function setLastAddedMessage(message: string | null) {
  setStoreState({ lastAddedMessage: message });
}

export function useCartStore() {
  const state = useSyncExternalStore(subscribeStore, getStoreSnapshot, getStoreSnapshot);
  return state;
}

export type CartNavTriggerProps = {
  labels: Pick<MiniCartLabels, "openCart">;
  cartIcon: ReactNode;
  className?: string;
  /** Visible text rendered beside the icon (header "Cart" label). */
  label?: ReactNode;
};

export function CartNavTrigger({ labels, cartIcon, className, label }: CartNavTriggerProps) {
  const { cart } = useCartStore();
  const count = getCartItemCount(cart);
  const badge =
    count > 0 ? (
      <span className="absolute -right-2 -top-1.5 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-bold leading-none text-[var(--primary-btn-fg)] ring-2 ring-surface">
        {count > 99 ? "99+" : String(count)}
      </span>
    ) : null;

  return (
    <button
      type="button"
      className={
        className ??
        "relative inline-flex min-h-11 min-w-11 items-center justify-center rounded text-primary"
      }
      aria-label={labels.openCart}
      data-testid="cart-nav-trigger"
      onClick={openMiniCart}
    >
      {/* The count sits on the icon itself; the label (if any) reads beside it. */}
      <span aria-hidden className="relative inline-flex">
        {cartIcon}
        {badge}
      </span>
      {label ? <span aria-hidden>{label}</span> : null}
    </button>
  );
}
