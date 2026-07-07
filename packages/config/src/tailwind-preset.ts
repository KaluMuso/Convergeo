type TailwindPreset = {
  content?: string[];
  theme?: Record<string, unknown>;
  plugins?: unknown[];
};

/**
 * Stub preset — M02-P01 will re-export the real tokens from `@vergeo/ui/tailwind-preset`.
 * Until then, apps can extend this empty preset without pulling UI components.
 */
const tailwindPreset: TailwindPreset = {
  content: [],
};

export default tailwindPreset;
