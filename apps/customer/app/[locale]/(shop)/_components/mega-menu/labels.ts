/**
 * Mega menu / drawer copy. Plain module (no "use client") so the server layout
 * can build the flat label object and hand it to the header as a prop.
 * Every string lives under `nav.megaMenu.*`; services/events vertical names are
 * mirrored there so the shop layout never has to ship the `services` / `events`
 * namespaces to every route.
 */
export const SERVICE_VERTICAL_SLUGS = [
  "beauty",
  "food-catering",
  "auto",
  "printing-creative",
  "home-services",
  "tech-services",
  "cleaning",
  "tailoring",
] as const;

export const EVENT_CATEGORY_SLUGS = [
  "workshops",
  "comedy-theatre",
  "pop-up-dinners",
  "cultural-arts",
  "lifestyle-community",
  "free-rsvp",
] as const;

/** Top-level product department slugs shown when the catalogue API is down. */
export const FALLBACK_ROOT_SLUGS = [
  "groceries-staples",
  "personal-care-beauty",
  "fashion",
  "electronics",
  "home-living",
  "office-stationery",
  "light-hardware",
] as const;

export type MegaMenuLabels = {
  /** Desktop trigger button text. */
  trigger: string;
  panelAria: string;
  loading: string;
  empty: string;
  railAria: string;
  groupProducts: string;
  groupServices: string;
  groupEvents: string;
  forYou: string;
  viewAll: string;
  browseFeatured: string;
  /** "View all in {name}" */
  viewAllIn: string;
  close: string;
  // Drawer
  menuOpen: string;
  drawerAria: string;
  mainMenu: string;
  back: string;
  helloGuest: string;
  /** "Hello, {name}" */
  helloUser: string;
  signIn: string;
  shopByDepartment: string;
  services: string;
  events: string;
  deals: string;
  sell: string;
  helpSettings: string;
  account: string;
  orders: string;
  help: string;
  seeAll: string;
  seeLess: string;
  /** "All in {name}" */
  allIn: string;
  serviceVerticals: Record<string, string>;
  eventCategories: Record<string, string>;
  fallbackRoots: Record<string, string>;
};

type Translator = {
  (key: string): string;
  raw: (key: string) => unknown;
};

/** Build the flat label bundle from a `nav`-namespace translator. */
export function buildMegaMenuLabels(t: Translator): MegaMenuLabels {
  const m = (key: string) => t(`megaMenu.${key}`);
  const raw = (key: string) => String(t.raw(`megaMenu.${key}`));
  const serviceVerticals: Record<string, string> = {};
  for (const slug of SERVICE_VERTICAL_SLUGS) {
    serviceVerticals[slug] = m(`serviceVerticals.${slug}`);
  }
  const eventCategories: Record<string, string> = {};
  for (const slug of EVENT_CATEGORY_SLUGS) {
    eventCategories[slug] = m(`eventCategories.${slug}`);
  }
  const fallbackRoots: Record<string, string> = {};
  for (const slug of FALLBACK_ROOT_SLUGS) {
    fallbackRoots[slug] = t(`shop.fallbackCategoryRoots.${slug}`);
  }
  return {
    trigger: t("shop.allCategories"),
    panelAria: t("shop.categoriesPanelAria"),
    loading: t("shop.categoriesLoading"),
    empty: t("shop.categoriesEmpty"),
    railAria: m("railAria"),
    groupProducts: m("groupProducts"),
    groupServices: m("groupServices"),
    groupEvents: m("groupEvents"),
    forYou: m("forYou"),
    viewAll: m("viewAll"),
    browseFeatured: m("browseFeatured"),
    viewAllIn: raw("viewAllIn"),
    close: m("close"),
    menuOpen: m("menuOpen"),
    drawerAria: m("drawerAria"),
    mainMenu: m("mainMenu"),
    back: m("back"),
    helloGuest: m("helloGuest"),
    helloUser: raw("helloUser"),
    signIn: m("signIn"),
    shopByDepartment: m("shopByDepartment"),
    services: m("services"),
    events: m("events"),
    deals: m("deals"),
    sell: m("sell"),
    helpSettings: m("helpSettings"),
    account: m("account"),
    orders: m("orders"),
    help: m("help"),
    seeAll: m("seeAll"),
    seeLess: m("seeLess"),
    allIn: raw("allIn"),
    serviceVerticals,
    eventCategories,
    fallbackRoots,
  };
}

/** Replace a single `{name}` placeholder. */
export function fillName(template: string, name: string): string {
  return template.replace("{name}", name);
}
