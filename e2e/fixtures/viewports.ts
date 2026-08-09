/**
 * Canonical viewport definitions for mobile-first release certification.
 * Used by mobile-layout and browse-journey specs across Playwright projects.
 */

export type ViewportSpec = {
  name: string;
  width: number;
  height: number;
  isMobile: boolean;
  hasTouch: boolean;
};

/** Minimum viewports required by the release certification scorecard. */
export const CERTIFICATION_VIEWPORTS: readonly ViewportSpec[] = [
  { name: "mobile-360", width: 360, height: 800, isMobile: true, hasTouch: true },
  { name: "mobile-390", width: 390, height: 844, isMobile: true, hasTouch: true },
  { name: "mobile-430", width: 430, height: 932, isMobile: true, hasTouch: true },
  { name: "tablet-768", width: 768, height: 1024, isMobile: true, hasTouch: true },
  { name: "desktop-1440", width: 1440, height: 900, isMobile: false, hasTouch: false },
] as const;

/** Minimum touch-target size per WCAG 2.2 AA (44×44 CSS px). */
export const MIN_TOUCH_TARGET_PX = 44;
