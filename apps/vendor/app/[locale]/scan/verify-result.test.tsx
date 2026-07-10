// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import vendorMessages from "../../../../../packages/i18n/messages/en/vendor.json";

import { VerifyResult } from "./_components/verify-result";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const scan = vendorMessages.scan as Record<string, unknown>;
    const parts = key.split(".");
    let current: unknown = scan;
    for (const part of parts.slice(1)) {
      if (!current || typeof current !== "object") {
        return key;
      }
      current = (current as Record<string, unknown>)[part];
    }
    if (typeof current === "string") {
      return current.replace(/\{(\w+)\}/g, (_, token: string) => values?.[token] ?? `{${token}}`);
    }
    return key;
  },
}));

afterEach(() => {
  cleanup();
});

describe("VerifyResult error states", () => {
  it("renders wrong-QR mismatch copy", () => {
    render(
      <VerifyResult
        state={{ kind: "error", errorKind: "wrong_qr" }}
        onScanAnother={() => undefined}
        onRetry={() => undefined}
      />,
    );

    expect(screen.getByTestId("scan-wrong-qr")).toBeInTheDocument();
    expect(screen.getByText(/Not a pickup code/i)).toBeInTheDocument();
    expect(screen.getByText(/event ticket/i)).toBeInTheDocument();
  });

  it("renders offline verify failure copy", () => {
    render(
      <VerifyResult
        state={{ kind: "error", errorKind: "offline" }}
        onScanAnother={() => undefined}
        onRetry={() => undefined}
      />,
    );

    expect(screen.getByTestId("scan-error")).toBeInTheDocument();
    expect(screen.getByText(/Cannot verify offline/i)).toBeInTheDocument();
  });
});
