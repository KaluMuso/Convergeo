/**
 * Frosted-glass surface helper. Pair with the `.v-glass*` classes in
 * styles/base.css (translucent --surface tint + backdrop blur + 1px light
 * border + soft shadow; opaque fallback without backdrop-filter or under
 * prefers-reduced-transparency / prefers-contrast:more).
 */
export type GlassVariant = "bar" | "bar-bottom" | "overlay" | "card";

export function glassClass(variant: GlassVariant = "overlay"): string {
  switch (variant) {
    case "bar":
      return "v-glass v-glass--bar";
    case "bar-bottom":
      return "v-glass v-glass--bar v-glass--bar-bottom";
    case "card":
      return "v-glass v-glass--card";
    default:
      return "v-glass v-glass--overlay";
  }
}
