import { type ReactElement } from "react";
import { describe, expect, it } from "vitest";

import { SeasonalThemeStyle } from "./seasonal-theme";

/** The component is pure (no hooks/effects), so calling it returns the element
 *  tree directly — no renderer needed to assert its shape. */
type StyleElement = ReactElement<{
  nonce?: string;
  "data-seasonal-theme"?: string;
  dangerouslySetInnerHTML: { __html: string };
}>;

describe("SeasonalThemeStyle", () => {
  it("renders nothing for the default preset", () => {
    expect(SeasonalThemeStyle({ preset: "slate" })).toBeNull();
    expect(SeasonalThemeStyle({ preset: undefined })).toBeNull();
    expect(SeasonalThemeStyle({})).toBeNull();
  });

  it("renders an inline <style> carrying the preset overrides", () => {
    const el = SeasonalThemeStyle({ preset: "harvest" }) as StyleElement;
    expect(el).not.toBeNull();
    expect(el.type).toBe("style");
    expect(el.props["data-seasonal-theme"]).toBe("harvest");
    expect(el.props.dangerouslySetInnerHTML.__html).toContain("--primary:#7a5214");
  });

  it("forwards a CSP nonce and resolves fuzzy config to a known id", () => {
    const el = SeasonalThemeStyle({ preset: "  MAUVE ", nonce: "n0nce" }) as StyleElement;
    expect(el.props.nonce).toBe("n0nce");
    // The stamped attribute is the resolved id, never the raw config.
    expect(el.props["data-seasonal-theme"]).toBe("mauve");
  });

  it("never stamps unresolved/hostile config onto the element", () => {
    // Unknown config resolves to the default ⇒ renders null, emits nothing.
    expect(SeasonalThemeStyle({ preset: "</style>" })).toBeNull();
  });
});
