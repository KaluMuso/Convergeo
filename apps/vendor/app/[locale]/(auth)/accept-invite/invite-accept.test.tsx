// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import auth from "../../../../../../packages/i18n/messages/en/auth.json";

import { InviteAcceptForm } from "./invite-accept-form";

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  verify: vi.fn(),
  session: vi.fn(),
  update: vi.fn(),
}));
vi.mock("@vergeo/auth/browser-client-lazy", () => ({
  getBrowserClient: mocks.client,
}));

const inviteSession = {
  user: { id: "invited-user" },
  access_token: "invite-session-token",
};

function show() {
  return render(
    <NextIntlClientProvider locale="en" messages={{ auth }}>
      <InviteAcceptForm locale="en" />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  window.history.replaceState({}, "", "/en/accept-invite");
  mocks.client.mockResolvedValue({
    auth: {
      verifyOtp: mocks.verify,
      getSession: mocks.session,
      updateUser: mocks.update,
    },
  });
  mocks.verify.mockResolvedValue({
    data: { session: inviteSession },
    error: null,
  });
  mocks.session.mockResolvedValue({ data: { session: inviteSession } });
  mocks.update.mockResolvedValue({ error: null });
});
afterEach(cleanup);

describe("vendor invite acceptance", () => {
  it.each([
    "/en/accept-invite",
    "/en/accept-invite?code=signin-code",
    "/en/accept-invite#token_hash=recovery-token&type=recovery",
    "/en/accept-invite#token_hash=invite-token&type=signup",
    "/en/accept-invite#type=invite",
  ])(
    "rejects missing or wrong-purpose links without touching Auth: %s",
    async (url) => {
      window.history.replaceState({}, "", url);
      show();
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "invalid or expired",
      );
      expect(mocks.client).not.toHaveBeenCalled();
      expect(mocks.update).not.toHaveBeenCalled();
      expect(window.location.hash).toBe("");
    },
  );

  it("verifies only an invite token, removes it from the URL, and sets a password once", async () => {
    window.history.replaceState(
      {},
      "",
      "/en/accept-invite#token_hash=invite-token&type=invite",
    );
    show();
    expect(
      await screen.findByRole("button", { name: "Set password" }),
    ).toBeInTheDocument();
    expect(mocks.verify).toHaveBeenCalledExactlyOnceWith({
      token_hash: "invite-token",
      type: "invite",
    });
    expect(window.location.href).toBe(
      `${window.location.origin}/en/accept-invite`,
    );
    fireEvent.change(screen.getByLabelText(/^New password/), {
      target: { value: "a-long-fixture-password" },
    });
    fireEvent.change(screen.getByLabelText(/^Confirm new password/), {
      target: { value: "a-long-fixture-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Set password" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Your password is set",
    );
    expect(mocks.update).toHaveBeenCalledExactlyOnceWith({
      password: "a-long-fixture-password",
    });
    expect(screen.getByRole("link", { name: "Go to sign in" })).toHaveAttribute(
      "href",
      "/en/login",
    );
  });

  it.each(["expired", "reused"])("rejects an %s invite token", async () => {
    mocks.verify.mockResolvedValue({
      data: { session: null },
      error: { message: "invalid token" },
    });
    window.history.replaceState(
      {},
      "",
      "/en/accept-invite#token_hash=invalid&type=invite",
    );
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid or expired",
    );
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it.each([
    ["different user", "other-user", "invite-session-token"],
    ["different token", "invited-user", "other-token"],
  ])(
    "fails closed with a %s before password setup",
    async (_, userId, accessToken) => {
      window.history.replaceState(
        {},
        "",
        "/en/accept-invite#token_hash=invite-token&type=invite",
      );
      show();
      await screen.findByRole("button", { name: "Set password" });
      mocks.session.mockResolvedValue({
        data: {
          session: { user: { id: userId }, access_token: accessToken },
        },
      });
      fireEvent.change(screen.getByLabelText(/^New password/), {
        target: { value: "fixture-password" },
      });
      fireEvent.change(screen.getByLabelText(/^Confirm new password/), {
        target: { value: "fixture-password" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Set password" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "invalid or expired",
      );
      expect(mocks.update).not.toHaveBeenCalled();
    },
  );

  it("does not verify after leaving during lazy client loading", async () => {
    let resolve!: (value: unknown) => void;
    mocks.client.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    window.history.replaceState(
      {},
      "",
      "/en/accept-invite#token_hash=invite-token&type=invite",
    );
    const view = show();
    view.unmount();
    await act(async () => resolve({ auth: { verifyOtp: mocks.verify } }));
    expect(mocks.verify).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it("ignores verification that finishes after leaving the page", async () => {
    let resolve!: (value: unknown) => void;
    mocks.verify.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    window.history.replaceState(
      {},
      "",
      "/en/accept-invite#token_hash=invite-token&type=invite",
    );
    const view = show();
    await waitFor(() => expect(mocks.verify).toHaveBeenCalledOnce());
    view.unmount();
    await act(async () =>
      resolve({ data: { session: inviteSession }, error: null }),
    );
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it("does not reuse a consumed invitation after an interrupted setup", async () => {
    window.history.replaceState(
      {},
      "",
      "/en/accept-invite#token_hash=invite-token&type=invite",
    );
    const view = show();
    await waitFor(() => expect(mocks.verify).toHaveBeenCalledOnce());
    view.unmount();
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "invalid or expired",
    );
    expect(mocks.verify).toHaveBeenCalledOnce();
    expect(mocks.update).not.toHaveBeenCalled();
    expect(
      screen.getByRole("link", { name: "Try password recovery" }),
    ).toHaveAttribute("href", "/en/reset-password");
  });
});
