import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ContactForm, type ContactFormLabels } from "./contact-form";

afterEach(cleanup);

const labels: ContactFormLabels = {
  nameLabel: "Your name",
  namePlaceholder: "name",
  contactLabel: "Contact",
  contactPlaceholder: "contact",
  messageLabel: "Message",
  messagePlaceholder: "message",
  requiredMarker: "*",
  submit: "Send message",
  submitting: "Sending",
  success: "Thanks",
  errorGeneric: "Something went wrong",
  errorRateLimited: "Too many",
  errorUnavailable: "Unavailable",
  validation: {
    nameRequired: "Please tell us your name.",
    nameTooLong: "Too long",
    messageRequired: "Please write a message.",
    messageTooShort: "Add more detail",
    messageTooLong: "Too long",
    contactTooLong: "Too long",
  },
};

describe("ContactForm", () => {
  it("shows validation errors and does not submit when empty", () => {
    render(<ContactForm labels={labels} />);
    fireEvent.submit(screen.getByRole("button", { name: labels.submit }).closest("form")!);
    expect(screen.getByText(labels.validation.nameRequired)).toBeInTheDocument();
    expect(screen.getByText(labels.validation.messageRequired)).toBeInTheDocument();
  });

  it("shows the translated unavailable message on a 503", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    render(<ContactForm labels={labels} />);
    fireEvent.change(screen.getByPlaceholderText(labels.namePlaceholder), {
      target: { value: "Chanda" },
    });
    fireEvent.change(screen.getByPlaceholderText(labels.messagePlaceholder), {
      target: { value: "Please help me with my order thanks." },
    });
    fireEvent.submit(screen.getByRole("button", { name: labels.submit }).closest("form")!);
    await waitFor(() => expect(screen.getByText(labels.errorUnavailable)).toBeInTheDocument());
    vi.unstubAllGlobals();
  });
});
