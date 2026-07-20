# UptimeRobot — Vergeo5 uptime monitoring (M16-P06)

External black-box monitoring for the Vergeo5 surfaces. When a monitor trips, UptimeRobot
POSTs to the n8n `uptime-alert` webhook, which pages the founder on WhatsApp
([`infra/n8n/uptime-alert.json`](./n8n/uptime-alert.json)). Error budget, thresholds, and
the paging rationale are in [`docs/ops/observability.md`](../docs/ops/observability.md).

**Founder-gated:** creating the account + monitors and firing a real alert needs a live
UptimeRobot account (free tier: 50 monitors, 5-min interval; Pro: 1-min). Nothing here is
secret and nothing is committed as a credential — the webhook URL and any API key stay in
the n8n environment only.

---

## Monitors

| #   | Monitor         | Type            | Target                                              | Interval | Up =                                                |
| --- | --------------- | --------------- | --------------------------------------------------- | -------- | --------------------------------------------------- |
| 1   | API health      | HTTP(s) keyword | `https://api.vergeo5.com/health`                    | 1 min    | HTTP 200 + body contains `ok`                       |
| 2   | Customer origin | HTTP(s)         | `https://vergeo5.com/en`                            | 1 min    | HTTP 200                                            |
| 3   | Vendor origin   | HTTP(s)         | `https://vendor.vergeo5.com/en`                     | 1 min    | HTTP 200                                            |
| 4   | Admin origin    | HTTP(s)         | `https://admin.vergeo5.com/en`                      | 5 min    | HTTP 200 / 401 (allowlist+Access may 401 the probe) |
| 5   | Payment webhook | HTTP(s) keyword | `https://api.vergeo5.com/health` (webhook liveness) | 1 min    | HTTP 200                                            |

Notes:

- Monitor 1 uses the **keyword** type so a 200 with a broken body still counts as down.
- Monitor 4 (admin) is IP-allowlisted behind Cloudflare Access, so a `401`/`403` from the
  probe is expected and treated as "reachable"; only a timeout / 5xx is "down". Keep it at
  a 5-min interval to avoid noise.
- Monitor 5 watches the payment webhook path's liveness. The webhook itself is idempotent
  and authenticated, so we monitor the API's health as its liveness proxy rather than
  POSTing a fake payment. If a dedicated unauthenticated webhook-ping route is added later,
  repoint this monitor at it.
- "Down" for paging = **2 consecutive** failed checks (see error budget).

---

## Alert contact (webhook → n8n → founder WhatsApp)

Add a single **Webhook** alert contact and attach it to every monitor above:

- **URL:** `https://n8n.vergeo5.com/webhook/uptime-alert` (the n8n workflow's production path)
- **Method:** `POST`, **JSON** payload (enable "Send as JSON").
- **Custom HTTP headers (required):**

  | Header            | Value                                         |
  | ----------------- | --------------------------------------------- |
  | `X-Uptime-Secret` | same value as n8n env `UPTIME_WEBHOOK_SECRET` |

  UptimeRobot → Alert Contact → advanced/custom headers (or “Send as HTTP headers”).
  Requests **without** this header, or with the wrong value, receive **401** and never
  page WhatsApp. The secret lives only in the n8n host environment — never in the
  committed workflow JSON.

- **POST value (JSON)** — non-sensitive health-monitor schema only:

  ```json
  {
    "monitorFriendlyName": "*monitorFriendlyName*",
    "monitorURL": "*monitorURL*",
    "alertType": "*alertType*",
    "alertDetails": "*alertDetails*",
    "alertDateTime": "*alertDateTime*"
  }
  ```

  UptimeRobot substitutes the `*...*` tokens. `alertType` is `1` for **down** and `2` for
  **up**; the n8n workflow only pages on `1`.

- Enable the contact for **Down** and **Up** events (n8n filters; the "up" event lets you
  extend the workflow with an all-clear later).

### Secret rotation & test-event procedure

1. Generate a new secret (`openssl rand -hex 32`) on the OCI host.
2. Set `UPTIME_WEBHOOK_SECRET` in the n8n container env (compose / `.env`), restart n8n.
3. Update the UptimeRobot alert contact `X-Uptime-Secret` header to the new value.
4. **Test event:** UptimeRobot → monitor → “Test Notification”, or:
   ```bash
   curl -sS -X POST https://n8n.vergeo5.com/webhook/uptime-alert \
     -H 'Content-Type: application/json' \
     -H "X-Uptime-Secret: $UPTIME_WEBHOOK_SECRET" \
     -d '{"monitorFriendlyName":"test","monitorURL":"https://api.vergeo5.com/health","alertType":"1","alertDetails":"manual test","alertDateTime":"now"}'
   ```
   Expect HTTP 200 and a WhatsApp page for `alertType=1`. Repeat with a wrong/missing
   header → HTTP 401 and **no** WhatsApp send. `alertType=2` with a valid secret → 200,
   `paged: false`.
5. Discard the previous secret after a successful test.

---

## Setup transcript (founder, one-time)

```
1. Sign up / log in at https://uptimerobot.com  (Pro plan for 1-min interval on 1,2,3,5).

2. My Settings → API → create a Main API Key (store in the n8n env only, if used;
   the webhook flow below needs no API key).

3. My Settings → Alert Contacts → Add Alert Contact
     Type:            Webhook
     Friendly Name:   Vergeo5 n8n uptime-alert
     URL to Notify:   https://n8n.vergeo5.com/webhook/uptime-alert
     POST value:      (the JSON block above)  ✅ Send as JSON
     → Save.

4. Dashboard → + Add New Monitor  (repeat for each row in the Monitors table):
     Monitor Type:        HTTP(s)   (or "Keyword" for #1 and #5, keyword = ok)
     Friendly Name:       <e.g. "API health">
     URL/IP:              <target from table>
     Monitoring Interval: 1 minute (5 for admin)
     Alert Contacts:      ☑ Vergeo5 n8n uptime-alert
     → Create Monitor.

5. In n8n, import infra/n8n/uptime-alert.json, set env
   UPTIME_WEBHOOK_SECRET / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_CLOUD_API_TOKEN /
   FOUNDER_WHATSAPP_TO, register the `ops_uptime_alert` WhatsApp template
   (founder action F5), configure the alert-contact header, then Activate.

6. Verify: UptimeRobot → a monitor → "Test Notification" (or pause the API briefly).
   Expect a WhatsApp message to the founder within ~2 minutes. Also confirm a request
   without `X-Uptime-Secret` returns 401.
```

**DEFERRED-AC (founder-gated):** step 6 — a real trip firing a real WhatsApp page —
requires the live UptimeRobot account + WhatsApp template and is verified by the founder.
