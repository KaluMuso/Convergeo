import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";

import socialMessages from "../../../../../../../packages/i18n/messages/en/social.json";

import { AddPeoplePanel } from "./add-people-panel";

vi.mock("../../../../../lib/social/contacts-api", () => ({
  contactsApi: {
    getPhoneDiscovery: vi.fn().mockResolvedValue({ enabled: false, pepper_configured: true }),
    getQr: vi.fn().mockResolvedValue({ handle: "demo", payload: "vgo:add:demo" }),
    sendRequest: vi.fn(),
    discoverHashes: vi.fn().mockResolvedValue({ items: [] }),
    setPhoneDiscovery: vi.fn(),
  },
}));

describe("AddPeoplePanel", () => {
  it("shows share fallback when Contact Picker is unsupported", async () => {
    render(
      <NextIntlClientProvider locale="en" messages={{ social: socialMessages }}>
        <AddPeoplePanel locale="en" siteOrigin="https://www.vergeo5.com" />
      </NextIntlClientProvider>,
    );
    expect(screen.getByTestId("share-fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("contact-picker-button")).not.toBeInTheDocument();
  });
});
