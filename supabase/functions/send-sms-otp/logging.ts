type LogFields = Record<string, string | number | boolean | null | undefined>;

export function maskPhoneTail(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 4) {
    return "****";
  }
  return `***${digits.slice(-4)}`;
}

export function logSmsOtpEvent(event: string, fields: LogFields = {}): void {
  console.log(JSON.stringify({ event, ...fields }));
}
