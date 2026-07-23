// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { PanelHero } from "./panel-hero";

const StubLink: ComponentType<{ href: string; className?: string; children: ReactNode }> = ({
  href,
  className,
  children,
}) => (
  <a href={href} className={className}>
    {children}
  </a>
);

describe("PanelHero", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders title and subtitle", () => {
    render(<PanelHero title="Directory" subtitle="Find vendors" />);
    expect(screen.getByRole("heading", { level: 1, name: "Directory" })).toBeInTheDocument();
    expect(screen.getByText("Find vendors")).toBeInTheDocument();
  });

  it("renders extra children and a CTA with pitch", () => {
    render(
      <PanelHero
        title="Services"
        subtitle="Hire pros"
        cta={{
          href: "/en/sell",
          label: "Become a provider",
          pitch: "It's free",
          LinkComponent: StubLink,
        }}
      >
        <p>128 results</p>
      </PanelHero>,
    );
    expect(screen.getByText("128 results")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "Become a provider" });
    expect(cta).toHaveAttribute("href", "/en/sell");
    expect(screen.getByText("It's free")).toBeInTheDocument();
  });

  it("omits the CTA row when no cta is provided", () => {
    render(<PanelHero title="Events" />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
