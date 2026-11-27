import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { glassClass } from "@vergeo/ui/src/glass";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, "..", "app", "[locale]", rel), "utf8");

describe("vendor glass surfaces", () => {
  it("uses the shared glass variants", () => {
    expect(glassClass("bar")).toContain("v-glass--bar");
    expect(glassClass("bar-bottom")).toContain("v-glass--bar-bottom");
    expect(glassClass("overlay")).toContain("v-glass--overlay");
  });

  it("paints the sticky header, bottom nav, more menu and order sheet with the glass utility", () => {
    const shell = read("_components/vendor-shell.tsx");
    expect(shell.match(/sticky top-0 z-40[^`]*\$\{glassClass\("bar"\)\}/g)).toHaveLength(2);
    const nav = read("_components/vendor-nav.tsx");
    expect(nav).toContain('className={glassClass("bar-bottom")}');
    expect(nav).toContain('glassClass("overlay")');
    expect(read("orders/_components/order-card.tsx")).toContain('glassClass("overlay")');
  });

  it("adds no ad-hoc colours: the old opaque surface classes are gone from those panels", () => {
    expect(read("_components/vendor-nav.tsx")).not.toMatch(
      /rounded-t-2xl border border-border bg-surface/,
    );
    expect(read("_components/vendor-shell.tsx")).not.toMatch(/border-b border-border bg-surface/);
  });
});
