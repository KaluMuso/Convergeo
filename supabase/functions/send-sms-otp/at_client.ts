export const AT_MESSAGING_URL = "https://api.africastalking.com/version1/messaging";

export type AtSendParams = {
  to: string;
  message: string;
  from: string;
  username: string;
  apiKey: string;
};

export type AtSendResult =
  { ok: true; status: number } | { ok: false; status: number; retryable: boolean; message: string };

export type AtFetch = typeof fetch;

export async function sendAtSms(
  params: AtSendParams,
  fetchImpl: AtFetch = fetch,
): Promise<AtSendResult> {
  const body = new URLSearchParams({
    username: params.username,
    to: params.to,
    message: params.message,
    from: params.from,
  });

  let response: Response;
  try {
    response = await fetchImpl(AT_MESSAGING_URL, {
      method: "POST",
      headers: {
        Accept: "application/json",
        apiKey: params.apiKey,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, status: 502, retryable: true, message };
  }

  if (response.ok) {
    return { ok: true, status: response.status };
  }

  const text = await response.text();
  const retryable = response.status >= 500;
  return {
    ok: false,
    status: response.status,
    retryable,
    message: text || `Africa's Talking HTTP ${response.status}`,
  };
}
