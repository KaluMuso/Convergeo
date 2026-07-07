export type ApiErrorEnvelope = {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id: string;
  };
};

export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    options: {
      requestId?: string;
      status?: number;
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = options.requestId ?? "unknown";
    this.status = options.status ?? 500;
    this.details = options.details ?? {};
  }
}

export type ApiClientOptions = {
  baseUrl: string;
  getToken?: () => string | null | Promise<string | null>;
};

function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== "object") {
    return false;
  }

  const error = (value as ApiErrorEnvelope).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof error.code === "string" &&
    typeof error.message === "string" &&
    typeof error.request_id === "string"
  );
}

export function createApiClient(options: ApiClientOptions) {
  const { baseUrl, getToken } = options;
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);

    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    if (getToken) {
      const token = await getToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
    }

    let response: Response;
    try {
      response = await fetch(`${normalizedBaseUrl}${path}`, {
        ...init,
        headers,
      });
    } catch {
      throw new ApiError("network_error", "Network request failed", { status: 0 });
    }

    const contentType = response.headers.get("content-type") ?? "";
    const isJson = contentType.includes("application/json");
    const payload: unknown = isJson ? await response.json() : null;

    if (!response.ok) {
      if (isApiErrorEnvelope(payload)) {
        throw new ApiError(payload.error.code, payload.error.message, {
          requestId: payload.error.request_id,
          status: response.status,
          details: payload.error.details ?? {},
        });
      }

      throw new ApiError("unknown_error", "Request failed", { status: response.status });
    }

    return payload as T;
  }

  return { request };
}
