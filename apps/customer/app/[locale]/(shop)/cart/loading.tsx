import { CartPageSkeleton } from "../_components/cart/cart-page-skeleton";

/**
 * Cart route skeleton — renders instantly while the server page resolves i18n labels.
 */
export default function CartLoading() {
  return (
    <div className="mx-auto w-full max-w-lg px-4 py-6 lg:max-w-5xl">
      <CartPageSkeleton />
    </div>
  );
}
