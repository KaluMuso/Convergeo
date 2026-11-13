export type AtEnvironment = "sandbox" | "live";

const AT_MESSAGING_PATH = "/version1/messaging";

const AT_HOSTS: Record<AtEnvironment, string> = {
  sandbox: "https://api.sandbox.africastalking.com",
  live: "https://api.africastalking.com",
};

export function resolveAtEnvironment(raw: string | undefined): AtEnvironment {
  const normalized = (raw ?? "").trim().toLowerCase();
  if (normalized === "sandbox" || normalized === "live") {
    return normalized;
  }
  throw new Error(
    `AT_ENVIRONMENT must be sandbox or live (got ${raw === undefined || raw === "" ? "missing" : "invalid"})`,
  );
}

export function resolveAtMessagingUrl(environment: AtEnvironment): string {
  return `${AT_HOSTS[environment]}${AT_MESSAGING_PATH}`;
}
