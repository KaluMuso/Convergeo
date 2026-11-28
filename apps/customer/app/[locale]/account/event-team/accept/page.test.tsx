import { describe, expect, it, vi } from "vitest";

import events from "../../../../../../../packages/i18n/messages/en/events.json";

vi.mock("next-intl/server", () => ({
  setRequestLocale: vi.fn(),
  getRequestConfig: (f: unknown) => f,
}));
vi.mock("./_components/event-team-accept-form", () => ({
  EventTeamAcceptForm: () => null,
}));

import EventTeamAcceptPage from "./page";

function texts(node: unknown, out: string[] = []): string[] {
  if (typeof node === "string") out.push(node);
  else if (Array.isArray(node)) node.forEach((n) => texts(n, out));
  else if (node && typeof node === "object" && "props" in node) {
    texts((node as { props: { children?: unknown } }).props.children, out);
  }
  return out;
}

describe("event-team accept page", () => {
  it("renders the translated title and intro, not message keys", async () => {
    const tree = await EventTeamAcceptPage({
      params: Promise.resolve({ locale: "en" }),
    });
    const all = texts(tree).join("|");
    expect(all).toContain(
      (events as unknown as { teamAccept: { title: string } }).teamAccept.title,
    );
    expect(all).not.toMatch(/teamAccept/);
  });
});
