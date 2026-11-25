/** Named icon tile hues — light/dark stroke colours for duotone icons. */
export const ICON_HUES = [
  "blue",
  "green",
  "amber",
  "orange",
  "red",
  "pink",
  "purple",
  "teal",
  "cyan",
  "slate",
] as const;

export type IconHue = (typeof ICON_HUES)[number];

export type IconHueTokens = {
  stroke: string;
  fill: string;
  tileBg: string;
};

export const ICON_HUE_LIGHT: Record<IconHue, IconHueTokens> = {
  blue: { stroke: "#2563EB", fill: "#2563EB33", tileBg: "#2563EB1F" },
  green: { stroke: "#16A34A", fill: "#16A34A33", tileBg: "#16A34A1F" },
  amber: { stroke: "#D97706", fill: "#D9770633", tileBg: "#D977061F" },
  orange: { stroke: "#EA580C", fill: "#EA580C33", tileBg: "#EA580C1F" },
  red: { stroke: "#DC2626", fill: "#DC262633", tileBg: "#DC26261F" },
  pink: { stroke: "#DB2777", fill: "#DB277733", tileBg: "#DB27771F" },
  purple: { stroke: "#9333EA", fill: "#9333EA33", tileBg: "#9333EA1F" },
  teal: { stroke: "#0D9488", fill: "#0D948833", tileBg: "#0D94881F" },
  cyan: { stroke: "#0891B2", fill: "#0891B233", tileBg: "#0891B21F" },
  slate: { stroke: "#475569", fill: "#47556933", tileBg: "#4755691F" },
};

export const ICON_HUE_DARK: Record<IconHue, IconHueTokens> = {
  blue: { stroke: "#60A5FA", fill: "#60A5FA33", tileBg: "#60A5FA1F" },
  green: { stroke: "#4ADE80", fill: "#4ADE8033", tileBg: "#4ADE801F" },
  amber: { stroke: "#FBBF24", fill: "#FBBF2433", tileBg: "#FBBF241F" },
  orange: { stroke: "#FB923C", fill: "#FB923C33", tileBg: "#FB923C1F" },
  red: { stroke: "#F87171", fill: "#F8717133", tileBg: "#F871711F" },
  pink: { stroke: "#F472B6", fill: "#F472B633", tileBg: "#F472B61F" },
  purple: { stroke: "#C084FC", fill: "#C084FC33", tileBg: "#C084FC1F" },
  teal: { stroke: "#2DD4BF", fill: "#2DD4BF33", tileBg: "#2DD4BF1F" },
  cyan: { stroke: "#22D3EE", fill: "#22D3EE33", tileBg: "#22D3EE1F" },
  slate: { stroke: "#94A3B8", fill: "#94A3B833", tileBg: "#94A3B81F" },
};

/** Top-level category slug → coloured icon tile. */
export const CATEGORY_ICON_MAP: Record<string, { hue: IconHue; icon: string }> = {
  beauty: { hue: "pink", icon: "sparkles" },
  health: { hue: "green", icon: "heart-pulse" },
  food: { hue: "orange", icon: "utensils" },
  fitness: { hue: "teal", icon: "dumbbell" },
  home: { hue: "amber", icon: "sofa" },
  auto: { hue: "slate", icon: "car" },
  electronics: { hue: "blue", icon: "smartphone" },
  fashion: { hue: "purple", icon: "shirt" },
  services: { hue: "cyan", icon: "wrench" },
  events: { hue: "red", icon: "calendar" },
  supplies: { hue: "amber", icon: "package" },
  default: { hue: "slate", icon: "layout-grid" },
};
