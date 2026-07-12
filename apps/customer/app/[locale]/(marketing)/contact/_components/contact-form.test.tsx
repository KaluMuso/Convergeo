import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
});
