# F4 — Escrow legal-review brief (for Zambian counsel)

**Status:** F4 is a **hard pre-real-money-launch gate** (`docs/plan/00-decisions.md` D14/F4; `docs/plan/launch-checklist.md` §0). Real money stays OFF (`public_launch=false`, prepaid collection disabled) until counsel signs this off. This brief is what you hand a Zambian payments/fintech lawyer so they can produce a written opinion.

**One-line ask to counsel:** *Confirm in writing whether Vergeo5 may operate its buyer-protection "escrow" and vendor settlement through Lenco (BroadPay Zambia, a BoZ-licensed Payment System Business) **without Vergeo5 itself holding a BoZ payment-service-provider or e-money licence** — and, if so, the exact contractual/structural conditions required.*

---

## 1. Why this is the launch blocker

- The **National Payment System Act No. 5 of 2026** (in force 8 April 2026) repealed and replaced the NPSA 2007. It licenses/designates/authorises "payment service providers," sets BoZ-determined minimum capital, and adds consumer-protection and market-conduct rules. E-money/mobile payments are further governed by the **E-Money Issuance Directives 2018** and the **ATM/POS/Internet/Mobile Payments Directives 2019**. *(Sources verified in `docs/plan/research/payments-compliance-zambia-2026-07.md` §5.)*
- There is **no published threshold or exemption** letting a marketplace hold/pool vendor funds unlicensed. A platform that itself **collects and holds money on behalf of vendors** risks meeting the PSP definition under the 2026 Act.
- The **standard compliant route** is to structure so a **BoZ-licensed aggregator receives, holds, and splits/settles** the funds, with the marketplace riding on that licence. Vergeo5's design (D14) intends exactly this — but "intends" is not "confirmed," and the money-path accounting (below) is close enough to holding client money that it must be blessed by counsel before real money flows.

## 2. The counterparty (funds handler)

**Lenco** is the flagship gateway of **BroadPay Zambia Ltd**, a **BoZ-licensed Payment System Business, Licence 02/PSB/2015** *(verified)*. Rails: MTN MoMo, Airtel Money, Zamtel Kwacha, Visa/Mastercard, bank transfer. Settlement: mobile money same-day, cards T+1. It exposes a public API for **collections, payouts, and bill payments**. Vergeo5 uses Lenco as its sole funds-handling layer (D11), behind an abstraction seam.

## 3. How money actually moves in the current build

*(Grounded in D5, D14, and `services/api/app/services/{ledger,escrow,payouts,refunds}`; confirm the banking reality in §5 Q0 with Lenco.)*

1. **Collect.** Buyer pays via Lenco (MoMo USSD-push, card widget, or bank). Funds settle to a **Lenco-managed account**, not a Vergeo5 commercial bank account. D14: *"Platform never pools funds in its own bank account."*
2. **Hold (escrow).** On `charge_received`, the platform's **double-entry ledger-of-record** posts the gross into an **`escrow` liability** against **`platform_cash`** — i.e. the money is recorded as *held on behalf of the buyer/vendor pending delivery*. Nothing is paid to the vendor yet.
3. **Release.** On delivery-confirmation (or **48h auto-confirm** after "delivered", or a 7-day-after-shipping fallback — D5), a guarded, audited state transition **captures platform commission** and **releases the net** to the vendor's `vendor_payable` account.
4. **Pay out.** The released net is disbursed to the vendor via the **Lenco payout API** (MoMo ≈ instant/≤5 min; bank 24–36h). Marketing promise: *"Paid out in minutes on mobile money — always within 48 hours."*
5. **Refunds.** Pre-release refunds come out of escrow; **post-release refunds claw back from the vendor's next payouts** (`refunds/payout_port.py`). COD (≤K500, D12) is modelled separately (`cod_receivable`), collected on delivery.

The legally-sensitive fact is step 2–4: between collection and payout, customer money is **held for a period** (hours to days) against a platform-maintained ledger that decides who gets paid. Whether that constitutes Vergeo5 "holding client money"/operating a payment system in the licensing sense — or is simply Vergeo5 **instructing** a licensed PSB that holds the funds — is the crux of F4.

## 4. The account-holder question (the pivot — confirm with Lenco first)

The whole analysis pivots on **who legally holds the funds between collection and payout**:

- **(A) Lenco/BroadPay is the legal custodian** — funds sit in a BroadPay-controlled account (or a segregated/trust account BroadPay operates under its own licence), and Vergeo5 only *instructs* releases/splits/payouts via API. → Strongest case that Vergeo5 rides on Lenco's licence and needs none of its own.
- **(B) Funds settle into a Vergeo5 account at/via Lenco that Vergeo5 controls**, and Vergeo5 pays vendors out of it. → Vergeo5 is closer to holding/pooling client money and may itself fall within the PSP/e-money definition, or need a trust/segregation arrangement.

**Get the definitive answer to (A) vs (B) from Lenco/BroadPay in writing before or alongside counsel** — it changes counsel's conclusion. The Vergeo5 design *intends* (A) (D14), but only the Lenco contract + account structure proves it.

## 5. Specific questions for counsel

0. **(Prerequisite, factual — from Lenco):** In the Lenco/BroadPay arrangement Vergeo5 will use, who is the legal account holder of collected funds between collection and vendor payout — BroadPay, or Vergeo5? Is there a trust/segregation of customer funds?
1. Under the **NPS Act No. 5 of 2026**, does Vergeo5's model (§3, on the (A) assumption) require Vergeo5 to hold a **payment-service-provider / payment-system-business designation or licence**, or does riding on BroadPay's Licence 02/PSB/2015 suffice?
2. Does holding buyer funds in "escrow" for up to ~48h–7 days (and 72h for used goods / T-7/T+1 for events, if later enabled) trigger the **e-money issuer** definition under the **E-Money Issuance Directives 2018**, or any BoZ authorisation?
3. What **contractual terms with BroadPay/Lenco** and **fund-segregation/trust safeguards** must be in place for the structure to be compliant (e.g. Lenco as merchant-of-record for the hold; segregated customer-funds account; refund/clawback authority)?
4. Are there **consumer-protection / market-conduct obligations** under the 2026 Act (disclosures, complaint handling, settlement-time commitments) that Vergeo5's escrow UX and the "always within 48 hours" payout promise must satisfy?
5. Does **COD** (cash collected by courier/vendor on delivery, ≤K500) change any of the above?
6. Any **CCPC** (consumer-protection) or data-protection (Zambia DPA) overlaps with the refund/escrow flow that counsel would flag?

## 6. What a GO opinion must confirm (so we can sign the F4 gate)

- Vergeo5 **does not** need its own BoZ PSP/e-money licence to run the escrow+settlement flow as described, **because** BroadPay/Lenco is the licensed funds handler — **stated with the conditions** (contract terms, account structure) that make it true; **or**
- A **named, bounded remediation** if not (e.g. execute a specific BroadPay agreement clause, move to a trust/segregated account, adjust settlement timing, or add a disclosure) — small enough to complete before launch.

## 7. Attachments to give counsel

- This brief + the money-flow summary (§3).
- The **Lenco/BroadPay merchant agreement** and the answer to §5 Q0 (account-holder/segregation).
- D5/D11/D12/D14 from `docs/plan/00-decisions.md` and the two-lane refund policy (D17).
- The verified regulatory sources in `docs/plan/research/payments-compliance-zambia-2026-07.md` §5 (NPS Act 2026 on ZambiaLII; BoZ e-money directives; BoZ designated-institutions list).

> This brief is **not legal advice** and states no legal conclusion — it frames the questions and the as-built facts so Zambian counsel can render the opinion that satisfies gate F4.
