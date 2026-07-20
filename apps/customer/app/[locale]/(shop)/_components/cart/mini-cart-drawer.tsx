"use client";

import { getBrowserClient } from "@vergeo/auth/browser-client-lazy";
import { ApiError } from "@vergeo/config";
import { formatK } from "@vergeo/i18n";
import { BottomSheet } from "@vergeo/ui/src/bottom-sheet";
import Link from "next/link";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { getApiBaseUrl } from "../../../../../lib/api-base-url";

export const FREE_DELIVERY_THRESHOLD_NGEWEE = 20_000;

export type ChangeNoticeKind = "price_changed" | "out_of_stock" | "qty_reduced";

export type ChangeNotice = {
  listing_id: string;
  kind: ChangeNoticeKind;
  requested_qty: number;
  available_qty: number | null;
  snapshot_price_ngwee: number;
  current_price_ngwee: number | null;
};

export type CartLine = {
  id: string;
  listing_id: string;
  vendor_id: string;
  qty: number;
  unit_price_ngwee: number;
  wholesale: boolean;
  line_total_ngwee: number;
  title_override: string | null;
};

export type VendorGroup = {
  vendor_id: string;
  items: CartLine[];
  subtotal_ngwee: number;
  delivery_eligible: boolean;
};

export type CartResponse = {
  cart_id: string;
  items: CartLine[];
  vendor_groups: VendorGroup[];
  subtotal_ngwee: number;
  conflicts: Array<{
    listing_id: string;
    code: string;
    message_key: string;
    details: Record<string, unknown>;
  }>;
  notices?: ChangeNotice[];
};

type RevalidateResponse = {
  notices: ChangeNotice[];
  has_changes: boolean;
};

type CartStoreState = {
  cart: CartResponse | null;
  notices: ChangeNotice[];
  loading: boolean;
  drawerOpen: boolean;
  lastAddedMessage: string | null;
};

type CartStoreListener = () => void;

async function getAccessToken(): Promise<string | null> {
  const supabase = await getBrowserClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function cartRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError("network_error", "Network request failed", { status: 0 });
  }

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload: unknown = isJson ? await response.json() : null;

  if (!response.ok) {
    if (
      payload &&
      typeof payload === "object" &&
      "error" in payload &&
      typeof (payload as { error?: { code?: string; message?: string } }).error?.code === "string"
    ) {
      const error = (payload as { error: { code: string; message: string; request_id?: string } })
        .error;
      throw new ApiError(error.code, error.message, {
        requestId: error.request_id,
        status: response.status,
      });
    }
    throw new ApiError("unknown_error", "Request failed", { status: response.status });
  }

  return payload as T;
}

async function fetchRevalidateNotices(): Promise<ChangeNotice[]> {
  try {
    const result = await cartRequest<RevalidateResponse>("/cart/revalidate", { method: "POST" });
    return result.notices ?? [];
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 405)) {
      return [];
    }
    return [];
  }
}

async function loadCartWithNotices(): Promise<{ cart: CartResponse; notices: ChangeNotice[] }> {
  const cart = await cartRequest<CartResponse>("/cart");
  if (cart.notices && cart.notices.length > 0) {
    return { cart, notices: cart.notices };
  }
  const notices = await fetchRevalidateNotices();
  return { cart, notices };
}

let storeState: CartStoreState = {
  cart: null,
  notices: [],
  loading: false,
  drawerOpen: false,
  lastAddedMessage: null,
};

const storeListeners = new Set<CartStoreListener>();

function emitStore() {
  storeListeners.forEach((listener) => listener());
}

function setStoreState(patch: Partial<CartStoreState>) {
  storeState = { ...storeState, ...patch };
  emitStore();
}

function subscribeStore(listener: CartStoreListener): () => void {
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
  return cart.items.reduce((sum, item) => sum + item.qty, 0);
}

export async function refreshCart(): Promise<CartResponse | null> {
  setStoreState({ loading: true });
  try {
    const { cart, notices } = await loadCartWithNotices();
    setStoreState({ cart, notices, loading: false });
    return cart;
  } catch {
    setStoreState({ loading: false });
    return null;
  }
}

export async function addCartItem(listingId: string, qty: number): Promise<CartResponse> {
  const cart = await cartRequest<CartResponse>("/cart/items", {
    method: "POST",
    body: JSON.stringify({ listing_id: listingId, qty }),
  });
  const notices = cart.notices ?? (await fetchRevalidateNotices());
  setStoreState({ cart, notices });
  return cart;
}

export async function updateCartItemQty(listingId: string, qty: number): Promise<CartResponse> {
  const cart = await cartRequest<CartResponse>(`/cart/items/${listingId}`, {
    method: "PATCH",
    body: JSON.stringify({ qty }),
  });
  const notices = cart.notices ?? (await fetchRevalidateNotices());
  setStoreState({ cart, notices });
  return cart;
}

export async function removeCartItem(listingId: string): Promise<CartResponse> {
  const cart = await cartRequest<CartResponse>(`/cart/items/${listingId}`, {
    method: "DELETE",
  });
  const notices = cart.notices ?? (await fetchRevalidateNotices());
  setStoreState({ cart, notices });
  return cart;
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

type CartContextValue = {
  refresh: () => Promise<CartResponse | null>;
  addItem: (listingId: string, qty: number) => Promise<CartResponse>;
  updateQty: (listingId: string, qty: number) => Promise<CartResponse>;
  removeItem: (listingId: string) => Promise<CartResponse>;
  openDrawer: () => void;
  closeDrawer: () => void;
};

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const value = useMemo<CartContextValue>(
    () => ({
      refresh: refreshCart,
      addItem: addCartItem,
      updateQty: updateCartItemQty,
      removeItem: removeCartItem,
      openDrawer: openMiniCart,
      closeDrawer: closeMiniCart,
    }),
    [],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCartActions(): CartContextValue {
  const context = useContext(CartContext);
  if (!context) {
    return {
      refresh: refreshCart,
      addItem: addCartItem,
      updateQty: updateCartItemQty,
      removeItem: removeCartItem,
      openDrawer: openMiniCart,
      closeDrawer: closeMiniCart,
    };
  }
  return context;
}

export type MiniCartLabels = {
  title: string;
  close: string;
  itemCount: string;
  subtotal: string;
  total: string;
  viewCart: string;
  checkoutCta: string;
  emptyTitle: string;
  emptyBody: string;
  emptyTrust: CartEmptyTrustLabels;
  browseCta: string;
  openCart: string;
};

export type CartEmptyTrustLabels = {
  escrow: string;
  delivery: string;
  pickup: string;
};

function EmptyCartIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5.5 6.5h13l-1.1 7.15a2 2 0 0 1-1.98 1.7H8.17a2 2 0 0 1-1.96-1.6L4.8 3.95H3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M9.2 19.25h.01M16 19.25h.01"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2.5"
      />
      <path d="m9 10.8 1.9 1.9 4.2-4.4" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function CartEmptyTrustList({
  labels,
  compact = false,
}: {
  labels: CartEmptyTrustLabels;
  compact?: boolean;
}) {
  const items = [labels.escrow, labels.delivery, labels.pickup];

  return (
    <ul
      className={
        compact
          ? "grid gap-2 text-left text-xs text-text-2"
          : "grid gap-2 text-left text-sm text-text-2 sm:grid-cols-3"
      }
      data-testid="cart-empty-trust-list"
    >
      {items.map((item) => (
        <li key={item} className="flex gap-2 rounded border border-border bg-surface p-3">
          <span
            className="mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-pill bg-primary-tint text-primary"
            aria-hidden="true"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path
                d="m3 6.2 1.8 1.8L9 3.8"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
              />
            </svg>
          </span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function MiniCartEmptyState({
  locale,
  labels,
  onBrowse,
}: {
  locale: string;
  labels: Pick<MiniCartLabels, "emptyTitle" | "emptyBody" | "browseCta" | "emptyTrust">;
  onBrowse?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 p-6 text-center" data-testid="mini-cart-empty">
      <div className="text-text-3">
        <EmptyCartIcon />
      </div>
      <div className="flex max-w-sm flex-col gap-2">
        <p className="font-display text-xl text-display-ink">{labels.emptyTitle}</p>
        <p className="text-sm text-text-2">{labels.emptyBody}</p>
      </div>
      <Link
        href={`/${locale}`}
        onClick={onBrowse}
        className="inline-flex h-11 min-h-11 items-center justify-center rounded border border-border bg-surface px-4 text-body font-medium text-text hover:bg-bg-2"
      >
        {labels.browseCta}
      </Link>
      <CartEmptyTrustList labels={labels.emptyTrust} compact />
    </div>
  );
}

export type CartNavTriggerProps = {
  labels: Pick<MiniCartLabels, "openCart">;
  cartIcon: ReactNode;
  className?: string;
};

export function CartNavTrigger({ labels, cartIcon, className }: CartNavTriggerProps) {
  const { cart } = useCartStore();
  const { openDrawer } = useCartActions();
  const count = getCartItemCount(cart);

  return (
    <button
      type="button"
      className={
        className ??
        "relative inline-flex min-h-11 min-w-11 items-center justify-center rounded text-primary"
      }
      aria-label={labels.openCart}
      data-testid="cart-nav-trigger"
      onClick={openDrawer}
    >
      <span aria-hidden>{cartIcon}</span>
      {count > 0 ? (
        <span className="absolute -right-0.5 -top-0.5 flex min-h-5 min-w-5 items-center justify-center rounded-pill bg-accent px-1 text-micro font-semibold text-surface">
          {count > 99 ? "99+" : String(count)}
        </span>
      ) : null}
    </button>
  );
}

type MiniCartDrawerProps = {
  locale: string;
  labels: MiniCartLabels;
};

export function MiniCartDrawer({ locale, labels }: MiniCartDrawerProps) {
  const { cart, drawerOpen } = useCartStore();
  const { closeDrawer } = useCartActions();
  const count = getCartItemCount(cart);

  useEffect(() => {
    void refreshCart();
  }, []);

  return (
    <BottomSheet
      open={drawerOpen}
      onClose={closeDrawer}
      title={labels.title}
      data-testid="mini-cart-drawer"
      snapHeight="70vh"
    >
      {cart && count > 0 ? (
        <div className="flex flex-col gap-4 p-4">
          <p className="text-sm text-text-2" data-testid="mini-cart-count">
            {labels.itemCount.replace("{count}", String(count))}
          </p>
          <ul className="flex flex-col gap-3">
            {cart.items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-3 text-sm">
                <span className="text-text">{item.title_override ?? item.listing_id}</span>
                <span className="shrink-0 font-mono text-text">
                  {formatK(item.line_total_ngwee)}
                </span>
              </li>
            ))}
          </ul>
          <div className="flex items-center justify-between border-t border-border pt-3">
            <span className="font-medium text-text">{labels.subtotal}</span>
            <span className="font-mono font-semibold text-text" data-testid="mini-cart-subtotal">
              {formatK(cart.subtotal_ngwee)}
            </span>
          </div>
          <div className="flex flex-col gap-2">
            <Link
              href={`/${locale}/checkout`}
              onClick={closeDrawer}
              className="inline-flex h-12 min-h-12 w-full items-center justify-center rounded bg-primary px-6 text-body font-medium text-surface hover:bg-primary-deep"
            >
              {labels.checkoutCta}
            </Link>
            <Link
              href={`/${locale}/cart`}
              onClick={closeDrawer}
              className="inline-flex h-11 min-h-11 w-full items-center justify-center rounded border border-border bg-surface px-4 text-body font-medium text-text hover:bg-bg-2"
            >
              {labels.viewCart}
            </Link>
          </div>
        </div>
      ) : (
        <MiniCartEmptyState locale={locale} labels={labels} onBrowse={closeDrawer} />
      )}
    </BottomSheet>
  );
}

export function CartHost({ locale, labels }: MiniCartDrawerProps) {
  const [, bump] = useReducer((value: number) => value + 1, 0);

  useEffect(() => {
    return subscribeStore(() => bump());
  }, []);

  return <MiniCartDrawer locale={locale} labels={labels} />;
}
