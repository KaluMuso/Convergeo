"""WAHA verified-vendor product intake (D35, Lane 2).

An isolated, flag-gated, **inbound-only** side-channel that lets an already
KYC-verified vendor send product photos/details over a 1:1 WhatsApp chat, which
the platform records as a **private intake record** for human review.

Hard boundaries (``docs/ops/waha-vendor-intake.md`` §5) — binding on every
module in this package:

* The official Meta Cloud API (Lane 1) remains the only customer/provider
  notification channel. Nothing here messages a customer.
* **Strictly inbound-only**: no acknowledgement, no reply, no outbound send of
  any kind. A future acknowledgement must be a separately designed official
  Cloud API/outbox capability, not a WAHA one.
* Groups, broadcast lists, channels, and statuses are dropped at ingestion.
* No OTP/auth, payment/payout/escrow, support/disputes, or moderation.
* An LLM may *suggest* structured fields; it never approves KYC, publication,
  payment, or moderation.
* Before M18-P05's guarded, vendor-confirmed handoff, nothing here creates,
  modifies, or publishes ``vendor_listings``.
"""
