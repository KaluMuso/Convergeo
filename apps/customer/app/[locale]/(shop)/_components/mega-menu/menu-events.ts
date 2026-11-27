/** One shared mobile drawer; header buttons and the bottom-nav tab open it by event. */
export const OPEN_MOBILE_MENU_EVENT = "vergeo:open-mobile-menu";

export function openMobileMenu(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(OPEN_MOBILE_MENU_EVENT));
  }
}

/** Fire-and-forget chunk preloads (called on intent so the first open is instant). */
export function preloadDesktopPanel(): void {
  void import("./mega-panel");
}

export function preloadMobileDrawer(): void {
  void import("./mobile-drawer");
}
