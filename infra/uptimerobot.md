# UptimeRobot — Vergeo5 uptime monitoring (M16-P06 / Prompt 9)

External black-box monitoring for the Vergeo5 surfaces. When a monitor trips, UptimeRobot
POSTs to the n8n `uptime-alert` webhook, which pages the founder on WhatsApp
([`infra/n8n/uptime-alert.json`](./n8n/uptime-alert.json)). Error budget, thresholds, and
the paging rationale are in [`docs/ops/observability.md`](../docs/ops/observability.md).

**Founder-gated:** creating the account + monitors and firing a real alert needs a live
UptimeRobot account (free tier: 50 monitors, 5-min interval; Pro: 1-min). Nothing here is
secret and nothing is committed as a credential — the webhook URL and any API key stay in
the n8n / UptimeRobot environment only.

---

## Monitors

| #   | Monitor                | Type            | Target                                 | Interval | Up =                                               |
| --- | ---------------------- | --------------- | -------------------------------------- | -------- | -------------------------------------------------- |
| 1   | Customer locale health | HTTP(s) keyword | `https://vergeo5.com/en/health`        | 1 min    | HTTP 200 + body contains `ok`                      |
| 2   | Vendor locale health   | HTTP(s) keyword | `https://vendor.vergeo5.com/en/health` | 1 min    | HTTP 200 + body contains `ok`                      |
| 3   | Admin locale health    | HTTP(s)         | `https://admin.vergeo5.com/en/health`  | 5 min    | HTTP 200 / 401 (Access/IP)                         |
| 4   | API healthz            | HTTP(s) keyword | `https://api.vergeo5.com/healthz`      | 1 min    | HTTP 200 + body contains `ok`                      |
| 5   | API readyz             | HTTP(s) keyword | `https://api.vergeo5.com/readyz`       | 1 min    | HTTP 200 + body contains `"status":"ok"`           |
| 6   | API search embedding   | HTTP(s) keyword | `https://api.vergeo5.com/readyz`       | 5 min    | HTTP 200 + body contains `"search_embedding":"ok"` |

Notes:

- Locale health routes return `{status, app, env, buildId}` — keyword `ok` catches broken bodies.
- Admin may 401 under Cloudflare Access / IP allowlist; treat timeout/5xx as down.
- `/readyz` returns `{status, search_rpc, search_embedding}`. Overall `status` is `ok` when
  Supabase **and** `search_rrf` RPC are reachable — **not** when only the embedding key is
  missing. That split is intentional: keyword search (FTS + pg_trgm) stays ready while the
  semantic lane is degraded.
- Monitor **#5** pages on true readiness failure (`status` or `search_rpc` degraded).
- Monitor **#6** is a **warn-only** contact (email/dashboard, not the WhatsApp paging webhook):
  `search_embedding=degraded` means `OPENROUTER_API_KEY` is unset/invalid — honest for LIVE-12,
  not a full API outage. Pair with `GET /search?q=…` and confirm `degraded:true` + non-empty
  results when investigating.
- "Down" for paging = **2 consecutive** failed checks (see error budget).

---

## Alert contact (webhook → n8n → founder WhatsApp)

Add a single **Webhook** alert contact and attach it to every monitor above:

- **URL:** `https://n8n.vergeo5.com/webhook/uptime-alert`
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
  **up**; the n8n workflow only pages on `1`, and only after the secret gate passes.

- Enable the contact for **Down** and **Up** events (n8n filters).

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
1. Sign up / log in at https://uptimerobot.com  (Pro plan for 1-min interval on 1,2,4,5).

2. Generate a high-entropy UPTIME_WEBHOOK_SECRET (openssl rand -hex 32).
   Set it in n8n env AND in the UptimeRobot webhook contact header.

3. My Settings → Alert Contacts → Add Alert Contact
     Type:            Webhook
     Friendly Name:   Vergeo5 n8n uptime-alert
     URL to Notify:   https://n8n.vergeo5.com/webhook/uptime-alert
     Custom headers:  X-Uptime-Secret: <same as n8n env>
     POST value:      (the JSON block above)  ✅ Send as JSON
     → Save.

4. Dashboard → + Add New Monitor  (repeat for each row in the Monitors table).

5. In n8n, import infra/n8n/uptime-alert.json, set env
   UPTIME_WEBHOOK_SECRET / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_CLOUD_API_TOKEN /
   FOUNDER_WHATSAPP_TO, register the `ops_uptime_alert` WhatsApp template
   (founder action F5), configure the alert-contact header, then Activate.

6. Verify auth fail-closed: POST without `X-Uptime-Secret` (or with the wrong value)
   returns 401 and sends no WhatsApp.
7. Verify: UptimeRobot → a monitor → "Test Notification" (or pause the API briefly).
   Expect a WhatsApp message to the founder within ~2 minutes. Record latency.
```

**DEFERRED-AC (founder-gated):** steps 6–7 require live UptimeRobot + WhatsApp template.
