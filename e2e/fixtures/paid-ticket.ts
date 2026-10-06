import type { Page } from "@playwright/test";
import { expect } from "./scanner-artifact-test";
import { customerOtp, flag, lenco, path, str } from "./env";
import { assertNoAccidentalRealMoney } from "./payment-fixtures";
import { nationalNumberFromE164 } from "./phone";
import { assertFixtureVersion, SEED } from "./seed";
import { assertPaidTicketSpine, type PaidTicketSpine } from "./paid-ticket-contract";

/** The fixed paid type in synthetic_contract.py; free RSVP has a distinct id. */
export const PAID_TICKET_TYPE_ID = "e3000000-0000-4000-8000-000000000001";

export function missingPaidPrerequisites(): string[] {
  return [
    ...(!flag("E2E_PAID_TICKET_PROVIDER_APPROVED") ? ["E2E_PAID_TICKET_PROVIDER_APPROVED"] : []),
    ...(!lenco.enabled ? ["LENCO_SANDBOX"] : []),
    ...(!lenco.secretKey ? ["LENCO_SANDBOX_SECRET_KEY"] : []),
    ...(!lenco.testMomoNumber ? ["LENCO_SANDBOX_MOMO_NUMBER"] : []),
    ...(!str("E2E_CUSTOMER_TEST_OTP") ? ["E2E_CUSTOMER_TEST_OTP"] : []),
    ...(!str("E2E_VENDOR_TEST_OTP") ? ["E2E_VENDOR_TEST_OTP"] : []),
    ...(!str("STAGING_SUPABASE_URL") ? ["STAGING_SUPABASE_URL"] : []),
    ...(!str("STAGING_SUPABASE_ANON_KEY") ? ["STAGING_SUPABASE_ANON_KEY"] : []),
  ];
}

type Purchase = PaidTicketSpine["purchase"];

function payerE164(value: string): string {
  const match = /^(?:\+260|0)?([79]\d{8})$/.exec(value.trim());
  if (!match) throw new Error("paid-ticket: invalid sandbox payer number");
  return `+260${match[1]}`;
}

/** Choose the real paid type in the public event picker and capture its minted order. */
export async function loginPaidBuyer(page: Page): Promise<void> {
  assertFixtureVersion();
  const destination = path(`/e/${SEED.event.slug}`);
  await page.goto(path(`/login?next=${encodeURIComponent(destination)}`));
  const phone = page.getByRole("textbox", { name: /phone|mobile/i });
  await expect(phone).toBeVisible();
  await phone.fill(nationalNumberFromE164(customerOtp.testPhone));
  await page
    .getByRole("button", { name: /continue|send|next|get code/i })
    .first()
    .click();
  await page.waitForURL(/\/otp(\?|$)/, { timeout: 20_000 });
  await page.getByRole("textbox", { name: "Digit 1 of 6" }).click();
  for (const digit of customerOtp.staticCode.slice(0, 6)) await page.keyboard.type(digit);
  await page.waitForURL((url) => url.pathname === destination, { timeout: 20_000 });
}

export async function buyPaidTicket(
  page: Page,
): Promise<{ purchase: Purchase; bearer: string; apiOrigin: string }> {
  await page.goto(path(`/e/${SEED.event.slug}`));
  const picker = page.locator('section[aria-labelledby^="ticket-picker-"]');
  await expect(picker).toBeVisible();
  const typeSelect = picker.locator("select").nth(1);
  await typeSelect.selectOption(PAID_TICKET_TYPE_ID);
  await expect(typeSelect).toHaveValue(PAID_TICKET_TYPE_ID);
  const responsePromise = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/tickets/checkout" &&
      response.request().method() === "POST",
  );
  await picker.getByRole("button", { name: /get ticket|pay|buy|book/i }).click();
  const response = await responsePromise;
  if (!response.ok())
    throw new Error(`paid-ticket: checkout request failed (${response.status()})`);
  const bearer = (await response.request().allHeaders()).authorization;
  if (!bearer?.startsWith("Bearer "))
    throw new Error("paid-ticket: authenticated purchase request missing");
  const purchase = (await response.json()) as Purchase;
  if (!purchase.checkout_group_id || !purchase.order_id || !purchase.order_item_id)
    throw new Error("paid-ticket: purchase response lacks order linkage");
  return { purchase, bearer, apiOrigin: new URL(response.url()).origin };
}

/** Native fetch keeps bearer, anon key, and wallet PIN out of Playwright steps. */
async function json<T>(
  url: string,
  bearer: string,
  anonKey?: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    redirect: "error",
    headers: {
      Accept: "application/json",
      Authorization: bearer,
      ...(anonKey ? { apikey: anonKey } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) throw new Error(`paid-ticket: read/payment API failed (${response.status})`);
  return response.json() as Promise<T>;
}

export async function settleSandboxTicket(
  apiOrigin: string,
  bearer: string,
  purchase: Purchase,
): Promise<PaidTicketSpine["payment"]> {
  if (!flag("E2E_PAID_TICKET_PROVIDER_APPROVED"))
    throw new Error("paid-ticket: explicit provider approval required");
  assertNoAccidentalRealMoney();
  await json(`${apiOrigin}/payments/retry`, bearer, undefined, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      checkout_group_id: purchase.checkout_group_id,
      payer_number: payerE164(lenco.testMomoNumber),
      rail: "mtn",
    }),
  });
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const payment = await json<PaidTicketSpine["payment"]>(
      `${apiOrigin}/payments/status?group=${encodeURIComponent(purchase.checkout_group_id)}`,
      bearer,
    );
    if (payment.status === "success") return payment;
    if (["failed", "expired", "cancelled", "cod"].includes(payment.status))
      throw new Error("paid-ticket: sandbox payment did not succeed");
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error("paid-ticket: sandbox payment settlement timed out");
}

export async function verifyPaidTicketSpine(
  apiOrigin: string,
  bearer: string,
  purchase: Purchase,
  payment: PaidTicketSpine["payment"],
): Promise<{ ticketId: string; pin: string }> {
  const supabase = str("STAGING_SUPABASE_URL").replace(/\/$/, "");
  const anonKey = str("STAGING_SUPABASE_ANON_KEY");
  async function row<T>(table: string, columns: string, filter: string): Promise<T> {
    const rows = await json<T[]>(
      `${supabase}/rest/v1/${table}?select=${columns}&${filter}`,
      bearer,
      anonKey,
    );
    if (!Array.isArray(rows) || rows.length !== 1)
      throw new Error(`paid-ticket: ${table} linkage row missing or ambiguous`);
    return rows[0];
  }
  const order = await json<PaidTicketSpine["order"]>(
    `${apiOrigin}/account/orders/${purchase.order_id}`,
    bearer,
  );
  const item = await row<PaidTicketSpine["item"]>(
    "order_items",
    "id,order_id,item_kind,qty,unit_price_ngwee",
    `id=eq.${encodeURIComponent(purchase.order_item_id)}`,
  );
  const line = await row<PaidTicketSpine["line"]>(
    "order_item_tickets",
    "order_item_id,ticket_type_id,instance_id",
    `order_item_id=eq.${encodeURIComponent(purchase.order_item_id)}`,
  );
  const type = await row<PaidTicketSpine["type"]>(
    "ticket_types",
    "id,event_id,kind,price_ngwee",
    `id=eq.${encodeURIComponent(line.ticket_type_id)}`,
  );
  const instance = await row<PaidTicketSpine["instance"]>(
    "event_instances",
    "id,event_id",
    `id=eq.${encodeURIComponent(line.instance_id)}`,
  );
  const event = await row<PaidTicketSpine["event"]>(
    "events",
    "id,slug,status",
    `id=eq.${encodeURIComponent(instance.event_id)}`,
  );
  const deadline = Date.now() + 90_000;
  let tickets: PaidTicketSpine["tickets"] = [];
  while (Date.now() < deadline) {
    tickets = await json<PaidTicketSpine["tickets"]>(
      `${supabase}/rest/v1/tickets?select=id,order_item_id,ticket_type_id,instance_id,status&order_item_id=eq.${encodeURIComponent(purchase.order_item_id)}`,
      bearer,
      anonKey,
    );
    if (tickets.length > 0) break;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  const wallet = (
    await json<{ tickets: PaidTicketSpine["wallet"] }>(`${apiOrigin}/account/tickets`, bearer)
  ).tickets;
  const ticketId = assertPaidTicketSpine({
    purchase,
    payment,
    order,
    item,
    line,
    tickets,
    type,
    instance,
    event,
    wallet,
    expected: {
      eventId: SEED.event.id,
      slug: SEED.event.slug,
      instanceId: SEED.event.instanceId,
      ticketTypeId: PAID_TICKET_TYPE_ID,
    },
  });
  const detail = await json<{
    id: string;
    pin: string | null;
    pin_available: boolean;
    status: string;
  }>(`${apiOrigin}/account/tickets/${ticketId}`, bearer);
  if (
    detail.id !== ticketId ||
    detail.status !== "issued" ||
    !detail.pin_available ||
    !/^\d{6}$/.test(detail.pin ?? "")
  )
    throw new Error("paid-ticket: purchased wallet credential unavailable");
  return { ticketId, pin: detail.pin! };
}
