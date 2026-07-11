"use client";

import { Button } from "@vergeo/ui/src/button";
import { FormField } from "@vergeo/ui/src/form-field";
import { Input } from "@vergeo/ui/src/input";
import { Textarea } from "@vergeo/ui/src/textarea";
import { useState, type FormEvent } from "react";

import { validateContact, type ContactErrorKey, type ContactErrors } from "./validation";

export type ContactFormLabels = {
  nameLabel: string;
  namePlaceholder: string;
  contactLabel: string;
  contactPlaceholder: string;
  messageLabel: string;
  messagePlaceholder: string;
  requiredMarker: string;
  submit: string;
  submitting: string;
  success: string;
  errorGeneric: string;
  errorRateLimited: string;
  validation: Record<ContactErrorKey, string>;
};

type Status = "idle" | "submitting" | "success" | "error";

export function ContactForm({ labels }: { labels: ContactFormLabels }) {
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<ContactErrors>({});
  const [status, setStatus] = useState<Status>("idle");
  const [formError, setFormError] = useState<string | null>(null);

  const errorText = (key: keyof ContactErrors): string | undefined => {
    const errorKey = errors[key];
    return errorKey ? labels.validation[errorKey] : undefined;
  };

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFormError(null);

    const result = validateContact({ name, contact, message });
    if (!result.ok) {
      setErrors(result.errors);
      return;
    }
    setErrors({});
    setStatus("submitting");

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result.value),
      });

      if (res.ok) {
        setStatus("success");
        setName("");
        setContact("");
        setMessage("");
        return;
      }

      setStatus("error");
      setFormError(res.status === 429 ? labels.errorRateLimited : labels.errorGeneric);
    } catch {
      setStatus("error");
      setFormError(labels.errorGeneric);
    }
  }

  if (status === "success") {
    return (
      <p
        className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-body text-text"
        role="status"
      >
        {labels.success}
      </p>
    );
  }

  return (
    <form className="flex flex-col gap-4" noValidate onSubmit={onSubmit}>
      <FormField
        label={labels.nameLabel}
        required
        requiredMarker={labels.requiredMarker}
        errorMessage={errorText("name")}
      >
        <Input
          name="name"
          value={name}
          error={Boolean(errors.name)}
          placeholder={labels.namePlaceholder}
          autoComplete="name"
          onChange={(event) => setName(event.target.value)}
        />
      </FormField>

      <FormField label={labels.contactLabel} errorMessage={errorText("contact")}>
        <Input
          name="contact"
          value={contact}
          error={Boolean(errors.contact)}
          placeholder={labels.contactPlaceholder}
          autoComplete="email"
          onChange={(event) => setContact(event.target.value)}
        />
      </FormField>

      <FormField
        label={labels.messageLabel}
        required
        requiredMarker={labels.requiredMarker}
        errorMessage={errorText("message")}
      >
        <Textarea
          name="message"
          value={message}
          rows={5}
          error={Boolean(errors.message)}
          placeholder={labels.messagePlaceholder}
          onChange={(event) => setMessage(event.target.value)}
        />
      </FormField>

      {formError ? (
        <p className="text-sm text-danger" role="alert">
          {formError}
        </p>
      ) : null}

      <Button
        type="submit"
        loading={status === "submitting"}
        loadingLabel={labels.submitting}
        className="self-start"
      >
        {labels.submit}
      </Button>
    </form>
  );
}
