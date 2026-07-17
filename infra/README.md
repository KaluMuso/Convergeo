# Vergeo5 OCI provisioning runbook

Reproducible staging/production bring-up for the API, Caddy, and n8n on an **OCI Always Free ARM VM** (Ampere A1: 4 OCPU / 24 GB RAM). Target budget ≤ **$50/mo** all-in (D6) — this stack uses Always Free compute + Cloudflare free + Vercel hobby until traffic requires Pro.

Customer app deploy is documented in `infra/vercel.md`. Vendor/admin Next.js standalone builds are served on the same VM behind Caddy (separate origins per D20/D21) — images/containers for those apps are documented here but not built in M01-P06.

## Prerequisites

- OCI account with Always Free Ampere capacity in your home region
- Domain `vergeo5.com` on Cloudflare (DNS + proxy)
- Supabase cloud project (URL + keys)
- GitHub deploy key or token to clone this repository
- Local machine with SSH client

## 1. Create the VM (OCI CLI)

```bash
# Example shape — adjust compartment, subnet, and image OCID for your tenancy/region
oci compute instance launch \
  --availability-domain "<AD-1>" \
  --compartment-id "<COMPARTMENT_OCID>" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus":4,"memoryInGBs":24}' \
  --display-name "vergeo5-staging" \
  --image-id "<ORACLE_LINUX_8_AARCH64_IMAGE_OCID>" \
  --subnet-id "<PUBLIC_SUBNET_OCID>" \
  --assign-public-ip true \
  --ssh-authorized-keys-file ~/.ssh/id_ed25519.pub
```

Note the public IP for Cloudflare A records (`infra/cloudflare-dns.md`).

## 2. Bootstrap Docker on the VM

```bash
ssh opc@<OCI_VM_PUBLIC_IP>

sudo dnf install -y docker-engine git
sudo systemctl enable --now docker
sudo usermod -aG docker opc

# Docker Compose plugin (v2)
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-aarch64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

newgrp docker
docker compose version
```

## 3. Clone and configure env

```bash
git clone https://github.com/KaluMuso/Convergeo.git vergeo5
cd vergeo5/infra

cp .env.example .env
chmod 600 .env
# Edit .env — fill names from .env.example (Supabase, n8n, domains, ADMIN_ALLOWED_IPS)
${EDITOR:-nano} .env
```

Set at minimum:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`
- `ENV=staging` (or `production`)
- `CORS_ORIGINS` including Vercel customer origin and vendor/admin hosts
- `ADMIN_ALLOWED_IPS` — space-separated CIDRs for admin allowlist
- `N8N_ENCRYPTION_KEY`, `N8N_BASIC_AUTH_USER`, `N8N_BASIC_AUTH_PASSWORD`

## 4. Validate compose + Caddy (on VM or CI)

```bash
docker compose config
docker run --rm \
  -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" \
  -e API_DOMAIN=api.vergeo5.com \
  -e VENDOR_DOMAIN=vendor.vergeo5.com \
  -e ADMIN_DOMAIN=admin.vergeo5.com \
  -e N8N_DOMAIN=n8n.vergeo5.com \
  -e ADMIN_ALLOWED_IPS="127.0.0.1/32" \
  caddy:2.9.1-alpine \
  caddy validate --config /etc/caddy/Caddyfile
```

## 5. Start the stack

The `api` image is prebuilt in CI and pushed to GHCR (`api-image.yml`), so the VM
pulls it rather than building in place (avoids OOM on the micro instance):

```bash
docker compose pull            # fetch the prebuilt api image + caddy/n8n
docker compose up -d           # no --build: run the pulled images
docker compose ps
docker compose logs -f api
curl -fsS http://localhost/healthz || curl -fsS http://127.0.0.1:8000/healthz
```

> Local dev (not the VM) can build from source instead: `docker compose up -d --build`.

Caddy obtains TLS certificates automatically once Cloudflare points to this host and ports 80/443 are open in the OCI security list.

## 6. Point Cloudflare DNS

Follow `infra/cloudflare-dns.md` to create proxied `A` records for `api`, `vendor`, `admin`, `n8n` → `<OCI_VM_PUBLIC_IP>` and apex/`www` → Vercel.

Set SSL/TLS mode to **Full (strict)**.

## 7. Deploy customer app to Vercel

Follow `infra/vercel.md` — connect the GitHub repo, set monorepo build commands, add `NEXT_PUBLIC_*` env vars only.

## 8. Vendor / admin on OCI (documented, not containerized in M01-P06)

Build standalone Next.js outputs on the VM or in CI, run on ports `3001` (vendor) and `3002` (admin), and set:

```bash
VENDOR_UPSTREAM=host.docker.internal:3001
ADMIN_UPSTREAM=host.docker.internal:3002
```

Caddy routes `vendor.vergeo5.com` and `admin.vergeo5.com` accordingly. Admin requests outside `ADMIN_ALLOWED_IPS` receive HTTP 403.

## Security checklist

- [ ] `infra/.env` mode `600`, never committed
- [ ] `SUPABASE_SERVICE_ROLE_KEY` only in API container env
- [ ] Admin allowlist CIDRs set; consider Cloudflare Access
- [ ] n8n basic auth enabled
- [ ] OCI security list: allow 22 from your IP only; 80/443 from Cloudflare IP ranges (or 0.0.0.0/0 if proxied-only)

## Operations

**Current production reality:** the live VM runs the API as a **standalone
container** (`vergeo5-api`) from the prebuilt GHCR image, bound to
`127.0.0.1:8000`, with **Caddy on the host** (systemd) proxying
`api.vergeo5.com` → `127.0.0.1:8000`. n8n is a container; there is no `api`
compose service in use on the VM. (`docker-compose.yml` remains the documented
full-stack/local reference — the API + Caddy there are containerized; the VM's
API + Caddy are not.)

Redeploy the API after a `services/api` change merges to master (CI has already
built `ghcr.io/kalumuso/convergeo-api:latest`) with the idempotent script — copy
`infra/redeploy-api.sh` to the VM and run it:

```bash
./redeploy-api.sh            # pull :latest, recreate vergeo5-api, wait for /healthz
./redeploy-api.sh <git-sha>  # pin / rollback to a specific build tag
```

It pulls **before** touching the running container, recreates it with the correct
bind (`127.0.0.1:8000`, overridable via `API_BIND`), health-checks `/healthz`, and
prints a rollback command if it fails. Do **not** hand-type a bare
`docker run … <flags> …` — a shell-interpreted placeholder can delete the
container without recreating it.

Verify publicly (the `related` path only exists in the current API build):

```bash
curl -fsS https://api.vergeo5.com/healthz
curl -fsS -o /dev/null -w '%{http_code}\n' https://api.vergeo5.com/products/rice-grains-standard/related
```

## Related docs

- `infra/ENVIRONMENTS.md` — environment matrix + secret placement
- `infra/cloudflare-dns.md` — DNS records
- `infra/vercel.md` — customer Vercel project
- `infra/n8n/README.md` — n8n container purpose
