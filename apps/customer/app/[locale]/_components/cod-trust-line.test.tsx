// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import commonBem from "../../../../../packages/i18n/messages/bem/common.json";
import commonEn from "../../../../../packages/i18n/messages/en/common.json";
import commonFr from "../../../../../packages/i18n/messages/fr/common.json";
import commonNya from "../../../../../packages/i18n/messages/nya/common.json";
import commonZh from "../../../../../packages/i18n/messages/zh/common.json";

import { CodTrustLine } from "./cod-trust-line";

afterEach(cleanup);

describe("CodTrustLine", () => {
  it("renders the shared COD line and never uses escrow wording", () => {
    render(<CodTrustLine text={commonEn.codTrust.line} />);
    const line = screen.getByTestId("cod-trust-line");
    expect(line).toHaveTextContent("You pay on delivery → We deliver → You confirm");
    expect(line).not.toHaveTextContent(/held by|you paid|released/i);
  });

  it("has real fr/zh copy and flagged English for bem/nya", () => {
    expect(commonFr.codTrust.line).not.toBe(commonEn.codTrust.line);
    expect(commonZh.codTrust.line).not.toBe(commonEn.codTrust.line);
    expect(commonBem.codTrust.line).toBe(`⚠ ${commonEn.codTrust.line}`);
    expect(commonNya.codTrust.line).toBe(`⚠ ${commonEn.codTrust.line}`);
  });
});
