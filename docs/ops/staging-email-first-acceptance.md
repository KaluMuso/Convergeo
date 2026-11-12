# Staging password diagnostic and disabled OTP source

This is a source and offline verification guide. No hosted login, email delivery, WhatsApp OTP delivery or protected release certification has been established by this integration. The owner has held publication, dispatch, credentials and provider activation. Keep those holds until separately released by the owner.

## Separate the two paths

The isolated email diagnostic uses the existing password-login UI for the fixed canonical synthetic customer and vendor personas. It sends no email OTP, magic link or reset mail; creates no account or password; and sits outside the protected 65-test matrix. Its successful result cannot replace checkout, payment, OTP, scanner, role or cleanup certification.

The ordinary protected staging graph retains its deployment, canonical setup, selected E2E and full release controls. Before deployment it now requires the same declarations as the accepted phone helpers: `SMS_OTP_TRANSPORT=waha`, `WAHA_OTP_ENABLED=true`, `STAGING_SMS_SANDBOX_ATTESTED=true` and `STAGING_TEST_OTP_MAP_ATTESTED=true`. These checks set nothing and inspect no hosted configuration. Defaults remain disabled/unverified. The existing sandbox and test-map declarations cannot be set merely to unblock email or compensate for a missing provider. A provider-neutral WhatsApp release certification still needs its own authorized qualification; this diagnostic supplies no waiver.

The Edge handler defaults to `SMS_OTP_TRANSPORT=disabled` on every project. Africa's Talking remains dormant unless explicitly selected as `at`; staging `at` additionally requires sandbox. WAHA requires the exact staging project, explicit `waha` selection and `WAHA_OTP_ENABLED=true`; it never falls back to SMS. Local `supabase/config.toml` hook syntax is not evidence of actual hosted switches. No flag, Auth setting, provider key or hosted workflow was changed here.

## Required owner handoff for a future diagnostic

The source accepts only the trusted manual `Protected staging operation` caller on the protected `staging` ref, with its exact workflow-code SHA and repository/run/attempt/SHA identity. The child uses the protected `staging` environment, read permissions and a narrow configuration map. The existing parent lock covers the complete operation; the child does not reacquire it.

After separate runtime approval, the owner must resolve these public dispatch inputs for the actual reviewed composed candidate:

- `focus_group=email-diagnostic` and full current `email_candidate_sha`.
- Exact successful manual `Deploy staging` source `email_source_run_id`, `email_source_run_attempt` and `email_source_artifact_id` for that SHA.
- `owner_provisioned_readiness=ready` only after confirming existing canonical synthetic accounts and private password configuration.
- `phone_transport_readiness=disabled` only after confirming actual hosted phone/SMS cannot send messages.
- `payment_outbound_readiness=verified-safe` only after confirming the staging sandbox target and disabled payout/dispatch/outbound settings.

The owner checks actual environment and credential issuance without disclosing values. In particular, payment sandbox labels/host guards do not prove the issuance of a stored token or test number. Preserve `ENV=staging`, sandbox-issued payment access, `PAYMENTS_ALLOW_PRODUCTION=false`, disabled outbound and payout settings, and inactive staging dispatch/payout workflows. No account reset, role/password update, credential creation/rotation or deployment is authorized by this guide. The canonical seed's confirmed synthetic email addresses do not establish that passwords have been provisioned.

Keep already approved password and bypass values only in protected configuration: `E2E_CUSTOMER_EMAIL_PASSWORD`, `E2E_VENDOR_EMAIL_PASSWORD`, the customer/vendor `VERCEL_AUTOMATION_BYPASS_SECRET_*` names and existing legacy fallback. Bind all three exact, distinct `VERCEL_PROJECT_ID_*` identities. Never put passwords, tokens, actual OTPs, session state or private response bodies in dispatch inputs, chat, source, logs or artifacts. A 401/protection refusal remains blocking; do not change access or substitute another environment to obtain a pass.

## What the source checks

The authenticated source run must belong to this repository and staging branch, use the manual deployment workflow, match the full candidate/attempt and finish successfully. All nine current-attempt deployment jobs must be uniquely successful. The selected nonexpired proof artifact must match its exact ID, run/attempt name, digest, bounded archive and smoke window. Proof age is at most 24 hours when validated near browser access. API source/image/Supabase plane and all three portal deployment, project and full health identities must match. Wrong or missing identities, stale proof, skipped migration and moved staging ref fail closed.

The graph skips deploy, canonical reset/E2E and certification for this scope. After dependency preparation it validates the handoff, rechecks staging ref before browser access, then invokes the U5 runner. That runner checks clean exact checkout SHA and both strict portal probes before starting isolated empty browser contexts. It first intercepts and aborts a dummy password request to prove the Auth destination before filling a private password. Allowed requests refuse redirects and retries; other writes, wrong planes, WebSockets, OTP/recovery/signup, provider and financial paths are blocked. The browser requires one fresh successful staging password receipt, bounded issuance/expiry and protected rendered content at the exact target. Decoded receipt checks do not grant role authority; existing server/middleware and Supabase boundaries remain authoritative.

Capture suppression, silent child output, no inherited debug hooks, no screenshots/traces/video and private error normalization protect failure paths. The workflow always attempts a post-access ref check and private metadata/result cleanup, uploads no diagnostic artifact and emits one sanitized completion even after authorization failure or skipped execution. Completion is always release-ineligible. Runner loss/cancellation still requires inspection; `always()` is not proof that cleanup ran.

## Independent WhatsApp decision

The inbound-only vendor-intake lane and its credentials are separate. The inactive signed OTP template and restricted replay schema are documented in [the WAHA handoff guide](../../infra/n8n/waha-otp-handoff.README.md). Auth remains the code generator/verifier/expiry authority. An ordinary WhatsApp connectivity message or corrected local receipt parser does not prove hosted OTP delivery or sign-in. Keep the workflow inactive, send disabled and credentials unbound until a separately approved privacy/runtime/recipient/replay/provider qualification.

## Qualification boundaries

CI retains Edge, mock protocol, email provenance, bootstrap, migration, RLS, RBAC, intake, all-app build/type and typegen gates. The phone helper's compiler-based offline tests run in the JavaScript job with the existing TypeScript dependency. The RLS Supabase CLI setup step is bounded at five minutes while retaining version `2.109.1`, unchanged retry logic and blocking RLS requirements. The observed setup stall's inner cause remains unconfirmed; a timeout produces failure, not a qualification exception.

Use the exact candidate's migration inventory and authenticated ledger/physical-state evidence for any later shared operation. The private OTP migration does not authorize a shared `db push`, whose pending chain can include other work. Cart and KYC remain separately owned. Full Supabase stack/RLS, actual environment readiness, runtime node/credential compatibility and protected browser certification remain independent gates; local mocks or PostgreSQL replay cannot stand in for them.
