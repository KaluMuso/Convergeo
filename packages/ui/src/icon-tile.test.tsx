// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

import { ICON_HUES } from "./icon-hues";
import { IconTile, type IconTileSize } from "./icon-tile";

const SIZES: IconTileSize[] = [32, 40, 48, 56];

describe("IconTile", () => {
  for (const hue of ICON_HUES) {
    for (const size of SIZES) {
      it(`renders ${hue} at size ${size}`, () => {
        render(
          <IconTile hue={hue} size={size}>
            <span data-testid="child" />
          </IconTile>,
        );
        const tile = screen.getByTestId("icon-tile");
        expect(tile).toHaveAttribute("data-hue", hue);
        expect(tile).toHaveAttribute("data-size", String(size));
        expect(screen.getByTestId("child")).toBeInTheDocument();
      });
    }
  }
});
