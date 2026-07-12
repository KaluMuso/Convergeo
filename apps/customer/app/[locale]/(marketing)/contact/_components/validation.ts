/** Shared contact-form validation — used by the client form and the server route. */

export const NAME_MAX = 80;
export const CONTACT_MAX = 120;
export const MESSAGE_MIN = 10;
export const MESSAGE_MAX = 2000;

export type ContactInput = {
  name?: unknown;
  contact?: unknown;
  message?: unknown;
};

export type ContactErrorKey =
  | "nameRequired"
  | "nameTooLong"
  | "messageRequired"
  | "messageTooShort"
  | "messageTooLong"
  | "contactTooLong";

export type ContactErrors = Partial<Record<"name" | "contact" | "message", ContactErrorKey>>;

export type SanitizedContact = {
  name: string;
  contact: string;
  message: string;
};

export type ContactValidation =
  { ok: true; value: SanitizedContact } | { ok: false; errors: ContactErrors };

const CONTROL_MAX = 0x1f;
const DEL = 0x7f;
const NEWLINE = 0x0a;

/** Collapse control characters (incl. CR/LF) to spaces — blocks email-header injection. */
function stripControlChars(value: string): string {
  let out = "";
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0;
    out += code <= CONTROL_MAX || code === DEL ? " " : ch;
  }
  return out.trim();
}

/** Drop control characters from the body but keep newlines (U+000A). */
function stripBodyControlChars(value: string): string {
  let out = "";
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0;
    if (code === NEWLINE) {
      out += ch;
    } else if (code > CONTROL_MAX && code !== DEL) {
      out += ch;
    }
  }
  return out.trim();
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function validateContact(input: ContactInput): ContactValidation {
  const name = stripControlChars(asString(input.name));
  const contact = stripControlChars(asString(input.contact));
  const message = stripBodyControlChars(asString(input.message));

  const errors: ContactErrors = {};

  if (name.length === 0) {
    errors.name = "nameRequired";
  } else if (name.length > NAME_MAX) {
    errors.name = "nameTooLong";
  }

  if (contact.length > CONTACT_MAX) {
    errors.contact = "contactTooLong";
  }

  if (message.length === 0) {
    errors.message = "messageRequired";
  } else if (message.length < MESSAGE_MIN) {
    errors.message = "messageTooShort";
  } else if (message.length > MESSAGE_MAX) {
    errors.message = "messageTooLong";
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }

  return { ok: true, value: { name, contact, message } };
}
