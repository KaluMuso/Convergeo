export type VerifyErrorKind =
  | "offline"
  | "wrong_qr"
  | "invalid_pin"
  | "already_claimed"
  | "stale_token"
  | "forbidden"
  | "generic";

export function classifyVerifyError(code: string, source: "qr" | "pin"): VerifyErrorKind {
  if (code === "network_error") {
    return "offline";
  }
  if (code === "pickup_invalid_pin") {
    return "invalid_pin";
  }
  if (code === "pickup_already_claimed") {
    return "already_claimed";
  }
  if (code === "pickup_token_stale") {
    return "stale_token";
  }
  if (code === "forbidden") {
    return "forbidden";
  }
  if (
    source === "qr" &&
    (code === "internal_error" ||
      code === "validation_error" ||
      code === "pickup_not_applicable" ||
      code === "not_found")
  ) {
    return "wrong_qr";
  }
  return "generic";
}

export function verifyErrorMessageKey(kind: VerifyErrorKind): string {
  switch (kind) {
    case "offline":
      return "scan.errors.offline";
    case "wrong_qr":
      return "scan.errors.wrongQr";
    case "invalid_pin":
      return "scan.errors.invalidPin";
    case "already_claimed":
      return "scan.errors.alreadyClaimed";
    case "stale_token":
      return "scan.errors.staleToken";
    case "forbidden":
      return "scan.errors.forbidden";
    default:
      return "scan.errors.verifyFailed";
  }
}
