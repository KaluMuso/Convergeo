import type { NavCategory } from "../category-tree";
import type { MegaMenuLabels } from "./labels";

export const TEST_LABELS: MegaMenuLabels = {
  trigger: "All Categories",
  panelAria: "All categories",
  loading: "Loading categories…",
  empty: "Categories are unavailable",
  railAria: "Browse departments",
  groupProducts: "Products",
  groupServices: "Services",
  groupEvents: "Events",
  forYou: "Categories for you",
  viewAll: "View all",
  browseFeatured: "Browse featured",
  viewAllIn: "View all in {name}",
  close: "Close menu",
  menuOpen: "Menu",
  drawerAria: "Main menu",
  mainMenu: "Main menu",
  back: "Back to main menu",
  helloGuest: "Hello, sign in",
  helloUser: "Hello, {name}",
  signIn: "Sign in or create account",
  shopByDepartment: "Shop by department",
  services: "Services",
  events: "Events",
  deals: "Deals",
  sell: "Sell on Convergeo",
  helpSettings: "Help & settings",
  account: "Your account",
  orders: "Your orders",
  help: "Help centre",
  seeAll: "See all",
  seeLess: "See less",
  allIn: "All in {name}",
  serviceVerticals: { beauty: "Beauty", auto: "Auto & mechanics" },
  eventCategories: { workshops: "Workshops & education" },
  fallbackRoots: {},
};

function dept(index: number, children: string[]): NavCategory {
  const slug = `dept-${index}`;
  return {
    id: `id-${index}`,
    name: `Department ${index}`,
    slug,
    children: children.map((name, i) => ({
      id: `id-${index}-${i}`,
      name,
      slug: `${slug}-${name.toLowerCase().replace(/\W+/g, "-")}`,
    })),
  };
}

/** Seven departments so "See all / See less" has something to collapse. */
export const TEST_TREE: NavCategory[] = [
  dept(1, ["Phones", "Laptops"]),
  dept(2, ["Rice", "Flour"]),
  dept(3, ["Tops"]),
  dept(4, ["Chairs"]),
  dept(5, ["Pens"]),
  dept(6, ["Hammers"]),
  dept(7, ["Paint"]),
];
