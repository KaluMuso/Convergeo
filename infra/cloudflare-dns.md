# Cloudflare DNS — Vergeo5

Orange-cloud (proxied) records unless noted. TLS mode: **Full (strict)** on OCI origins once Caddy serves valid certs.

## Records

| Name     | Type  | Target                 | Proxied | Notes                                                                    |
| -------- | ----- | ---------------------- | ------- | ------------------------------------------------------------------------ |
| `@`      | CNAME | `cname.vercel-dns.com` | Yes     | Customer app (Vercel). Apex → Vercel per Vercel docs.                    |
| `www`    | CNAME | `cname.vercel-dns.com` | Yes     | Redirect/www mirror for customer.                                        |
| `api`    | A     | `<OCI_VM_PUBLIC_IP>`   | Yes     | FastAPI via Caddy → `api:8000`.                                          |
| `api`    | AAAA  | `<OCI_VM_IPV6>`        | Yes     | Optional if OCI VM has IPv6.                                             |
| `vendor` | A     | `<OCI_VM_PUBLIC_IP>`   | Yes     | Vendor Next.js standalone behind Caddy.                                  |
| `admin`  | A     | `<OCI_VM_PUBLIC_IP>`   | Yes     | Admin origin — separate host + IP allowlist (D20).                       |
| `n8n`    | A     | `<OCI_VM_PUBLIC_IP>`   | Yes     | n8n UI (auth required). Restrict further via Cloudflare Access optional. |

## WAF / caching posture (free tier)

- **Customer (`vergeo5.com`)**: Vercel edge cache + ISR; Cloudflare only on apex if using CNAME flattening.
- **API (`api.vergeo5.com`)**: Cloudflare proxy for DDoS/WAF-lite; **cache bypass** on API routes (respect `Cache-Control` from FastAPI).
- **Vendor/Admin**: short TTL or bypass cache (authenticated tools).
- **Admin**: consider Cloudflare Access policy in addition to Caddy `remote_ip` allowlist.

## CLI example (illustrative)

```bash
# Requires CLOUDFLARE_API_TOKEN with Zone.DNS edit on vergeo5.com
export ZONE_ID="<cloudflare_zone_id>"

curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"type":"A","name":"api","content":"<OCI_VM_PUBLIC_IP>","proxied":true}'
```

Repeat for `vendor`, `admin`, `n8n`. Configure apex/`www` CNAMEs to Vercel per `infra/vercel.md`.
