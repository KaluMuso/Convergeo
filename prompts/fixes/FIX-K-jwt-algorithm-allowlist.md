> **Prepend `prompts/_header.md`.** Branch from + PR against **`master`**. **Touch ONLY the files below.** **⚙ do NOT use `git stash`.** **No migration.** **Auth-critical — run the full auth test suite before reporting.** Foreground blocking calls only.

# FIX-K — Narrow the JWT algorithm allow-list to match the JWKS verifier (🟠 MED, security hardening)

## Finding (from the 2026-07-21 docs/ops audit)

`services/api/app/core/auth.py::verify_supabase_jwt` (~L41) passes `algorithms=["RS256", "ES256", "HS256"]` while resolving the signing key from Supabase **JWKS** (`_jwks_client` / `get_signing_key_from_jwt`, ~L28-36) — i.e. asymmetric keys. Including **HS256** (symmetric) on a JWKS verifier is the classic **algorithm-confusion** smell: a forged `HS256` token could try to use a public key as the HMAC secret. PyJWT mitigates this (it rejects an asymmetric key used as an HMAC secret), so it is **not exploitable in practice**, but it contradicts `docs/ops/owasp-audit.md` (A02 documents `RS256/ES256`) and should be removed if the project issues asymmetric JWTs.

## Required fix (self-verifying — safe only for asymmetric-JWT projects)

1. Change the allow-list to `algorithms=["RS256", "ES256"]`.
2. Add/extend a test proving a **valid current Supabase access token still verifies** end-to-end (use the existing auth test fixtures / a token signed with the JWKS key type your project uses).
3. **Guard rail:** if that test fails because real tokens are `HS256` (a legacy shared-secret Supabase project), **REVERT** the change, keep `HS256`, and instead open a note that HS256 is intentional — do NOT ship broken auth. (This is unlikely: the current JWKS-only key resolution would already be broken for a legacy HS256 project, which implies the project is asymmetric.)

## Files (ONLY)

- Modify `services/api/app/core/auth.py`
- Extend `services/api/tests/test_auth_dep.py` (or the auth verification test file)
- **Do NOT touch** anything else.

## Tests (RUN)

- A valid RS256/ES256 Supabase token verifies and yields the expected `sub`/roles.
- A tampered/expired/wrong-issuer token → 401 (existing coverage must still pass).
- An `HS256`-alg'd token is rejected.
- **Full auth suite** + `ruff` + `mypy`.

## Report

STATUS / FILES / DEVIATIONS (confirm the project is asymmetric-JWT, or state you reverted) / TESTS (paste the valid-token-still-verifies result) / EXCERPT the changed line / QUESTIONS.
