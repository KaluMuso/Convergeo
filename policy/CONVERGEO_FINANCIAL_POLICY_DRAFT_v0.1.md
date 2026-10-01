# Convergeo — Financial Operations and Customer Protection Policy

DRAFT v0.1 | 29 September 2026 | NOT EFFECTIVE

> DRAFT: not owner-approved, provider-cleared, counsel-approved, effective or a money/deployment authorization.

## Convergeo

_THE HUB OF LOGOS_

### Financial Operations and Customer Protection Policy

Paid products, services, events and wholesale inventory

> DRAFT v0.1 | 29 September 2026 | NOT EFFECTIVE
> Prepared for owner, implementation, provider and Zambian legal review. This is a new drafting proposal, not the previously asserted counsel-reviewed policy and not authorization to activate money.

| Document control                          | Value                                                |
| ----------------------------------------- | ---------------------------------------------------- |
| Policy identifier                         | CG-FIN-OPS-0.1                                       |
| Sponsor                                   | Kaluba Prosper Musonda                               |
| Operating legal entity                    | TO BE CONFIRMED before customer publication          |
| Owner decision / signature                | PENDING                                              |
| Provider and legal review                 | PENDING; reviewer identities and references required |
| Effective date / production configuration | NOT SET / NOT AUTHORIZED                             |
| Engineering baseline                      | PR #715: 8f78448e4b340787fae98eeee58c372cc5ded307    |
| Coordination source                       | GitHub issue #716; allocation checkpoint 5885685575  |

### How to use this draft

Engineers may continue the already assigned protective-invariant repairs and isolated tests. They must not load proposed commercial settings into a live environment or describe this document as approved. Owners should complete decisions Q1–Q6; counsel and the provider should resolve the clearance checklist. A signed decision does not substitute for code, schema, sandbox or deployment evidence.

When an authentic existing approved policy is supplied, compare it clause by clause. Preserve its version and approval record. Do not silently replace it with this proposal or overwrite terms already accepted by buyers and vendors.

Source distinction: S1–S5 are supplied/repository materials; R1–R8 are external references checked for this draft. Proposed terms are marked as proposals. “Must” expresses the intended control after adoption or an already assigned technical safety invariant; it is not evidence that code implements the control.

## 01 | Authority, scope and operating model

_CONTROL BASIS AND LEGAL BOUNDARY_

### FP-01 | Scope and hierarchy

Cover one marketplace order or service job even when money spans multiple checkout groups, deposits, balances, vendors or ticket allocations. The first commercial release remains paid products, services and events together. COD and free RSVP can retain their legitimate uses, but do not certify a paid journey. n8n remains on Hetzner. These are preserved project decisions, not new commercial elections. [S3]

Applicable mandatory law and valid provider/account restrictions cannot be overridden by this draft. Within those constraints, use the actual approved operating policy and the buyer/vendor terms accepted for that transaction. Resolve conflicts explicitly; do not let a code default, old strategy example or agent instruction silently become policy.

### FP-02 | Meaning of escrow and custody

The code term “escrow” describes an internal ledger allocation or release restriction. It does not prove legal trust status, safeguarded or segregated accounts, insolvency protection, a payment-services authorization, deposit insurance or a right to hold merchants’ money. Do not market any of those properties without documentary support.

Before money activation, the operating entity must obtain a documented determination covering its merchant-of-record/agency/marketplace role, Lenco account terms, permitted collection and onward payout structure, any required Bank of Zambia authorization, safeguarding obligations and permitted hold periods. Keep restricted customer/vendor balances unavailable for operating expenditure. This control does not itself create legal segregation. [R1, R2]

### FP-03 | Immutable commercial snapshot

Before an order/quote is accepted, disclose the seller, deliverable, total price, currency, taxes and delivery charges, deposit and balance amounts, payment schedule, commission/fee treatment where relevant, cancellation terms and release conditions. Retain the exact policy and quote versions, acceptance evidence and server-calculated monetary snapshot.

Do not impose a new price, recipient, fee, due date or cancellation rule retrospectively. Changes require the applicable lawful variation and fresh recorded consent. Preserve historical evidence; do not rewrite the accepted snapshot to fit a new policy.

> Unresolved commercial values are not zero or “free.” A missing approved rate, time window, account mapping or rule blocks only the affected live action. It does not block synthetic isolated testing or the existing safety repairs.

## 02 | Verified funding and uncertainty

_TECHNICAL SAFETY REQUIREMENTS_

### FP-04 | A receipt, not a button press, establishes funding

A browser callback, screenshot, local paid flag, HTTP 200 or balanced journal does not alone establish collection. Validate an authoritative provider observation against the stored obligation: reference, provider identity, amount, currency, account/merchant binding and applicable rail. Missing or inconsistent evidence remains unresolved. Card fulfilment additionally requires the canonical server-side collection query. [S1, Implemented behavior; S2, D1–D3; S5]

Verify provider events and preserve their provenance before asynchronous processing. Repeated observations must not duplicate collection allocation, issuance, release, refunds or notifications. Failed/invalid evidence cannot be promoted to accepted receipt evidence. Polling supplements webhook delivery; it is not a second financial authority. [R3, R4]

| Observed state                         | Required operational meaning                                                                     |
| -------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Successful and identity-matched        | Allocate once to the correct obligation; separately evaluate settlement and release eligibility. |
| Pending / authorization outstanding    | Retain the original attempt and reference. Do not claim payment or create a competing attempt.   |
| Authoritative failed                   | Record failure with matching evidence. Apply only the approved eligibility/retry rule.           |
| Not found                              | Record that lookup result. It is not proof that a previously sent request had no effect.         |
| Timeout / transport / invalid response | Record uncertainty or invalid evidence. No assumed success, refund completion or blind resend.   |

### FP-05 | Financial amounts and evidence conservation

Use integer ngwee internally and exact decimal conversion at the provider boundary. Preserve purchase-time arithmetic and rounding rules. Keep provider fees, platform charges, taxes and vendor entitlements distinguishable. Never create a monetary receipt to repair an accounting mismatch or to make a test green.

One genuine provider movement may allocate across legitimate linked order lines; it must not be counted multiple times. Distinct provider movements must not be collapsed merely because they share a merchant reference. Overpayment or late collection is an explicit obligation/exception with an owner, not disposable excess revenue.

> Provider documentation supports interface expectations, not transaction acceptance. Public transfer schemas include accountId, creditAccount, amount, currency, reference and lencoReference; actual merchant/sandbox responses still need verification. [R3]

## 03 | Service deposits, balances and acknowledgement

_TECHNICAL INVARIANTS + Q1/Q2 PROPOSALS_

### FP-06 | Distinct obligations, one service relationship

Keep a durable link among job, accepted quote, order, deposit/balance obligation, checkout group, payment attempt, provider receipt and allocation. Each nonzero payable leg has its own validated reference and accepted-funding evidence. Preserve the one-accepted-collection-per-checkout invariant; do not disguise a balance as a replay of the deposit. Zero-value legs must be represented as not due, not with invented receipts. [S1, Implemented behavior and Migration proposal]

### Proposed Q1-A | Agreed quote schedule

For newly accepted pilot quotes, disclose the total and seller/customer-agreed deposit; do not impose a universal deposit percentage. Proposed sequencing: a deposit, where required by the quote, becomes payable on acceptance; the standard remaining balance becomes payable after the provider records work done and the buyer acknowledges it. A different contractual milestone must be explicitly approved and recorded rather than inferred. No further collection is initiated without the buyer’s applicable authorization.

This sequencing is NOT yet approved and must not be used to remove the balance-first safety regression. Even where a new request should have been disallowed, a genuine balance receipt must still be recognized for cancellation, refund, reconciliation and exception handling.

### FP-07 | Four different states

| State                 | Meaning                                                                                                     |
| --------------------- | ----------------------------------------------------------------------------------------------------------- |
| Work marked done      | The provider reports performance; no proof of funding or buyer agreement is created.                        |
| Buyer acknowledgement | Records the buyer’s response and can invoice the agreed balance; it does not create cash.                   |
| Financially funded    | All currently required amounts have valid receipt/allocation evidence; holds remain independently relevant. |
| Released / paid out   | Release eligibility has been satisfied; actual provider payout is separately tracked and verified.          |

Interactive confirm and automatic workers must use the same under-lock funding, hold and authorization rules. Neither may manufacture CHARGE_RECEIVED or release the full job value after deposit-only funding. Do not claim the vendor has been paid merely because an internal release journal exists.

### Proposed Q2-A | Silence prompts follow-up, not release

During the initial pilot, buyer silence generates reminders and an operator case, not automatic acknowledgement, collection or release. Any future automatic-completion period needs a named duration, notice rules, appeal path and approval; genuine funding and holds remain mandatory.

> Synthetic fixture only: 100000 ngwee total, 30000 deposit, 70000 balance, and 1200 basis points commission are existing test values. They are not an approved price, deposit ratio or Convergeo fee. [S1, Evidence and limits]

## 04 | Cancellation, disputes and refunds

_TECHNICAL SAFETY + Q5 PROPOSAL_

### FP-08 | Any funded leg matters

Cancellation/rejection must examine every valid linked payment obligation, including the original checkout and a separate service balance. “Any money requires financial resolution” is not the same test as “enough money permits completion.” Recheck the decision within a common lock protocol with claims, receipt settlement, refund reservation and release. Preserve all evidence and ordinary product/event/COD behavior. [S1, Continuation checkpoint; S4]

| Situation                                  | Required treatment                                                                                              |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| No funding, no uncertain attempt           | Cancel according to applicable terms; prohibit new initiation after terminalization.                            |
| Attempt is pending or outcome unknown      | Stop new initiation, retain reconciliation and assign the unresolved case. Do not assert that no money arrived. |
| Deposit only, balance only, or both funded | Use the refund/financial-resolution path across all linked genuine funding; never ignore a leg.                 |
| Late receipt after cancellation/expiry     | Record a durable collection exception without resurrecting fulfilment or freely releasing funds.                |
| Refund races release                       | One coordinated decision owns the value; no double spend or duplicate disposition.                              |
| Wrong-owner or unrelated link              | Reject as authority evidence; do not count another customer’s payment.                                          |

### FP-09 | Refund entitlement and refund execution are separate

Record the reason, legal/contractual basis, entitled amount, source funding, already completed refunds, reserved/in-flight refunds, chargebacks and other recoveries. Prevent duplicate recovery and cumulative excess. Where the marketplace owes compensation beyond received principal, record a distinct authorized liability; do not relabel compensation as a reversal of nonexistent collection.

Refund approved, refund reserved, refund submitted and refund successfully delivered are distinct states. Do not mark completion from disappearance of a pending row. After release, record the actual clawback/merchant liability and funding source; do not fabricate a pre-release escrow reversal or use unrelated customer funds.

### Proposed Q5-A | No new platform cancellation penalty in pilot

No new platform-imposed cancellation penalty is proposed for the initial pilot. Partial performance, custom work, delivery costs and other lawful deductions require the accepted terms and documented case evidence. Seller/platform failure, non-delivery and defect remedies must not be replaced by a blanket “no refunds” condition. Mandatory consumer rights and provider/card rules prevail. [R5, R6]

A dispute or chargeback creates a proportionate documented hold and an owner/review date. Buyers and sellers receive the reason and next step where legally permitted. A platform complaint deadline must not extinguish rights that law or card/provider rules preserve.

## 05 | Products, wholesale and events

_VERTICAL-SPECIFIC PROPOSED TERMS_

### FP-10 | Products and wholesale

Bind delivery, pickup, stock reservations and release evidence to the actual vendor order and fulfilment group. On collection failure or uncertainty, do not claim prepaid fulfilment is authorized. COD remains its own explicit collection flow, not a substitute for paid-provider certification.

For wholesale, disclose minimum quantities, tiers, location/fulfilment, lead times and any quote-specific deposit terms before acceptance. A business account label alone must not be used to assume that every consumer-protection obligation disappears. Custom-made, perishable, digital and regulated products need reviewed category terms; a universal platform “no return” rule is not proposed.

### Proposed Q3-A | Evidence-based product release

For the pilot, use buyer-confirmed delivery/pickup or a documented operator dispute resolution, together with verified funding, settled/available funds where required, commission rules and all holds. Do not introduce a new automatic elapsed-time release. Record acknowledgement separately from any financial state and preserve later mandatory remedies.

### FP-11 | Paid events and ticket evidence

Issue the exact paid ticket quantity only after genuine authorized funding; repeat issuance must not create extra tickets. A free RSVP or scanner fixture is not paid-ticket evidence. Preserve holder/attendee authorization and confidential PIN/QR handling. [S2 paid-event acceptance]

### Proposed Q4-A | Full post-event release for pilot

Select the existing full-release branch for new pilot events: not before the actual event end plus its disclosed 24-hour threshold, and only after the funding, dispute, refund, settlement and payout conditions also pass. This 24-hour value is a proposed election of a reported existing branch, not a legal minimum, a new provider promise or an already approved owner term. Pre-event/phased advances are not proposed for the first pilot and require a separate agreement if retained.

An organizer cancellation or material postponement/change creates a documented buyer-remedy process under the accepted terms and applicable law. Do not silently roll a ticket into a new event or retain charges without authority. Time-based release evidence in a live sandbox must use real elapsed time; controlled clocks belong in separately labelled tests.

> Existing accepted transactions are not retroactively switched to Q3/Q4 by publishing this draft. Any mismatch between the proposed pilot profile and existing behavior is recorded for owner approval and implementation, not silently waived.

## 06 | Transfers, release and commission

_TECHNICAL SAFETY + Q6 PROPOSAL_

### FP-12 | Durable outbound obligations

Before the first transfer POST, persist the intended source account, beneficiary/destination, amount, currency, merchant reference and dispatch ownership. Concurrent workers must not each claim first send. Treat crashes after claim or submission as potentially sent unless reliable evidence establishes otherwise. Preserve immutable intent even when a vendor later edits their account.

Pending, timeout and ambiguous post-attempt not-found states must not trigger a blind second POST. Query the original reference, retain observations and escalate when unresolved. An authoritative failed reference must not be reused unless Lenco confirms a safe supported process; any linked new attempt retains the original obligation and audit chain. One failed batch item must not suppress independent healthy items. [S2 D1–D2; R3]

Before paid/refund-complete status and financial posting, require provider-successful evidence matched to amount, currency, merchant/provider reference, debit account and destination. Normalize only using documented rules; never substitute missing provider fields with intended request values and call that independent verification.

### FP-13 | Refund channel and chargeback interaction

The repository describes refunds as transfers, but that does not authorize every refund channel. Confirm the permitted route for each rail, particularly hosted-card payments. Prefer the provider/card-rule-compatible original-payment route; any permitted alternative requires payer verification, explicit recorded consent, destination checks and controls against a later card chargeback causing double recovery. Do not ask operators to obtain raw PAN/CVV or paste card data into chat. [S5]

### FP-14 | Eligible release is not cash availability

Compute releasable value from valid receipts, order allocations, completed and reserved refunds, disputes, charges and prior release effects without double-counting classifications. Verify provider available/settled funds independently of the internal ledger. Do not release or pay out uncollected service balances, unrestricted unrelated balances, or money covered by an unresolved hold.

Commission rates, caps, tax treatment and fee allocation remain UNSPECIFIED here. Apply an approved immutable order/job snapshot; do not copy the 1200-bps test fixture into live configuration. Operational commission capture does not settle the accounting/tax question of revenue recognition; the accountant must map that treatment.

### Proposed Q6-A | Staffed payout batch

Process eligible pilot payouts in the next staffed business-day batch after documented authorization and reconciliation. This is a proposed internal processing cadence, not a promise of beneficiary arrival. Exceptional refunds, beneficiary changes and hold overrides require a second authorized reviewer. No one may approve their own exceptional change; absence of a reviewer queues it rather than removes the control.

## 07 | Reconciliation, legacy state and reporting

_F3 IMPLEMENTATION BASIS_

### FP-15 | One account and complete movement coverage

Use the configured and verified merchant account, not the first account returned by an API. Read every required transaction page and preserve a reporting cutoff/time zone. Match by provider transaction identity and the relevant merchant/obligation/payment/transfer links. Aggregate legitimate allocations; retain genuinely distinct provider movements, unparsed references and all unresolved exceptions. [S2 D5–D6]

The reconciliation bridge must separately explain opening funds, collected gross, fees, unsettled/settled amounts, refunds, payouts, chargebacks and adjustments. A global zero-sum ledger or available-balance equality without that bridge is insufficient. A fee discrepancy remains a discrepancy until explained; do not add a balancing plug.

Retain immutable original daily reports and correction versions. Do not delete yesterday’s report to force a clean rerun. Preserve evidence linking the report, source/schema version, account/cutoff, provider rows and ledger movements. The API/database remains authoritative; n8n only schedules authorized jobs and records results.

### FP-16 | Historical funding is not repaired by relabelling it

Metadata-only adoption may link unambiguous legacy service records, but must not invent a provider receipt, successful payment, settled amount or canonical card-query proof. Unclear mappings enter a held review queue. Genuine preexisting receipts and their ledger fingerprints must survive the upgrade. [S1, Migration proposal and shared interfaces]

For a historical fabricated balance journal, preserve the journal and the discovered discrepancy. Determine the economic position with authorized financial/legal review, then post an approved correcting entry and liability treatment with links to the original evidence. Do not erase the journal, backdate a provider confirmation or treat deployment rollback as reversing actual money.

### FP-17 | Evidence required for release decisions

Record source commit/tree, migration set, deployed identities, actor/role, obligation and provider correlators, verified business outcome, timestamps, ledger effect, test method and result. Distinguish mock, controlled replay, real isolated database, provider sandbox, staging and production. Missing, skipped or xfailed mandatory scenarios cannot yield full acceptance.

> Accepted baseline: the 88-case real-stack gate has separate published evidence. F1’s two and F2’s 13 currently declared cases need actual execution on the financial candidate; those counts are not a ceiling and the repeated fresh/upgrade runs are not extra unique cases. [S1, Evidence and limits; S4]

## 08 | Operators, incidents and personal data

_PROPOSED INTERNAL CONTROL CLAUSES_

### FP-18 | Primary and backup operations

Use named, separate operator accounts for the primary and backup staff member, with least privilege and multi-factor authentication where supported. Keep authority, coverage and handover responsibilities documented. A role named “admin” must not allow direct insertion of trusted webhook evidence, receipt fabrication or arbitrary release.

Each exceptional financial action records requester, reviewer, reason, affected obligation, intended value/destination, policy basis and execution result. An alert or WhatsApp reaction is not an approval. A normal automated worker may execute an already authorized obligation only within the approved gates; human approval must not bypass invariant checks.

### FP-19 | Incident containment

On suspected duplicate transfer, unexplained cash shortfall, lost credential, wrong account binding or unauthorized receipt, stop affected new initiation/dispatch and preserve evidence. Keep safe reads, observation capture and reconciliation available when possible. Assign an owner, review interval and restoration criteria. Restoring service requires a tested remediation and documented authorization, not simply clearing an error flag.

Proposed pilot support targets, subject to operator approval: acknowledge a financial complaint within one staffed business day and provide a progress update at least every two staffed business days while unresolved. These are not statutory deadlines or a guarantee of provider refund arrival. Identify the published staffed hours and route urgent incidents to the backup operator.

### FP-20 | n8n, notifications and confidential data

Keep n8n on Hetzner and route financial work through scoped authenticated API jobs. Do not introduce direct SQL money-state writers. Retain actual scheduled executions, failure/retry outcomes and alert acknowledgements. One operational failure must not silently disable all payment recovery.

Send only a minimal incident ID, severity, safe status and authenticated case link to an authorized notification channel. Never include API tokens, JWTs, webhook signatures, customer identifiers beyond necessity, bank details, card data or ticket secrets. Verify that the selected WhatsApp integration actually supports the intended destination; this document does not assert group delivery is available. Queue an unsent alert rather than switch to an unauthorized channel.

Before live processing, map storage locations, processors, lawful bases, access controls, retention/deletion duties and legal holds for Hetzner, Supabase, Vercel, Lenco and messaging. Confirm the applicable data-controller/processor registration and cross-border requirements. Do not invent a universal retention period or assume overseas hosting is automatically compliant. [R7, R8]

## 09 | Owner decision register

_ALL OPTIONS BELOW ARE PROPOSED, NOT APPROVED_

Select one option per row or provide a replacement. “A” is the proposed initial pilot profile; choosing it is an owner business decision, not legal/provider clearance or deployment authorization. Unselected fields remain pending. Existing contracts retain their applicable terms.

| ID                       | Proposed A                                                                                                                | Alternative / decision needed                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Q1 Service chargeability | Per accepted quote; no universal deposit %. Standard balance payable after provider work-done and buyer acknowledgement.  | B: other explicit milestone schedule. Supply exact trigger and buyer consent rule.                |
| Q2 Buyer silence         | Reminders and manual resolution; no new automatic collection or release.                                                  | B: automatic completion after approved duration/notices, with all funding/hold controls retained. |
| Q3 Product release       | Buyer delivery/pickup acceptance or documented operator resolution; no new timed auto-release.                            | B: define evidence, duration, notices and appeals for a timed release.                            |
| Q4 Event release         | Existing full post-event branch: end +24 hours, with all additional gates; no pilot advance.                              | B: a reviewed phased/pre-event schedule, cap/reserve and cancellation funding plan.               |
| Q5 Cancellation charges  | No new platform cancellation penalty in pilot. Preserve lawful, agreed, evidence-supported partial-performance treatment. | B: supply category-specific fee/deduction schedule and consumer-law review.                       |
| Q6 Payout operations     | Next staffed business-day batch for eligible funds; second reviewer for exceptions/beneficiary changes/hold overrides.    | B: define another cadence, authorization model and risk thresholds.                               |

### Amounts and account rules intentionally not invented

Commission schedules, minimum/maximum ticket/order values, provider fees, platform fee bearing, taxes, payout minimums, reserves and retention periods require an actual approved schedule or written “not applicable” decision. Different business categories may have different accepted schedules. A missing value never silently selects a synthetic example.

### Approval record to return

Owner choices: Q1=___ Q2=___ Q3=___ Q4=___ Q5=___ Q6=___
Rate/schedule reference: ___
Support/coverage reference: ___
Authorized second reviewer role: ___
Policy version and scope approved: ___
Owner name/date: ___
Legal/provider clearances: separately pending unless evidence attached.

> Engineering may implement the already assigned safety invariants and test proposed options in isolated fixtures while these decisions are pending. Do not hard-code A into production, remove an existing release branch without approval, or claim this blank form is consent.

## 10 | Draft customer and vendor wording

_NOT FOR CUSTOMER PUBLICATION UNTIL APPROVED_

These clauses are proposed wording for later terms/help pages. Insert the operating legal entity, support route and approved schedules before publication. They do not replace a complete legal terms-of-service, privacy notice, vendor contract or mandatory disclosures.

### C-01 | Payment status

“Your payment is complete only when we verify the payment provider’s result against your order. A pending or confirming message is not a final paid receipt. When an attempt is still unresolved, please use its status/retry controls rather than starting another payment. We will preserve the original reference while we investigate.”

### C-02 | Services and the outstanding balance

“Before you accept a service quote, we will show the total, any deposit, the remaining balance and when each amount becomes payable. Marking work done or acknowledging it does not itself charge you or create a payment. We will show any amount still due and provide the applicable payment action. Funds are not released merely because a completion button was pressed.”

### C-03 | Cancellations and refunds

“Cancellation may still require a financial resolution when any part of your order has been paid or a payment is pending. We will assess the applicable terms, payment evidence and legal rights. An approved refund is shown separately from one submitted to, or successfully completed by, the payment provider. A refund timing estimate depends on the confirmed route; we do not describe an unresolved transfer as completed.”

### C-04 | Problems with products, services or events

“Report non-delivery, defects, service issues or event changes using [APPROVED SUPPORT ROUTE]. We may hold the affected amount while the case is examined. We will explain the next step and request only necessary evidence. These procedures do not remove rights you have under applicable law or relevant payment/card rules.”

### V-01 | Vendor proceeds

“A sale notification, internal pending balance or release entry is not proof that a payout reached you. Proceeds are subject to verified collection, the accepted fee schedule, applicable settlement, refunds, disputes, reserves and eligibility checks. We send payouts only to the verified beneficiary recorded for the approved transfer obligation.”

### V-02 | Changes and partial work

“A change to scope, price, deposit, balance, delivery or cancellation conditions requires the applicable buyer agreement before it is charged. Record performed work and supporting evidence for partial-service disputes. Do not ask support to mark an unpaid balance paid, reassign an uncertain transfer or circumvent a hold.”

> Do not promise licensed escrow, insured funds, immediate settlement, a fixed refund arrival time or universal “non-refundable” charges from this draft. Put the approved policy version and schedule into the transaction snapshot, not only a changeable help page.

## 11 | Policy-to-test acceptance map

_IMPLEMENTATION CONTRACT, NOT A CLAIM OF PASS_

The following controls turn policy language into testable acceptance. Map each to the actual source/RPC and a retained test result. An owner-approved proposal still needs implementation and execution evidence.

| ID / owner     | Required case                                                                       | Evidence boundary                                                      |
| -------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| PF-01 / F1     | Provider HTTP success with business failed; typed not-found versus transport error. | Real adapter/caller with controlled HTTP; actual provider later.       |
| PF-02 / F1     | Concurrent first-send claims; crash/lost response; pending must not repost.         | Independent database connections and counted outbound calls.           |
| PF-03 / F1     | Wrong/missing amount, currency, source account, reference or recipient.             | No paid/refund-complete state or payout journal.                       |
| PF-04 / F1+F2  | FAILED poll includes identity evidence; missing evidence cannot enable retry.       | Actual poller-to-state consumer on combined source.                    |
| PF-05 / F2     | None, deposit-only, balance-only and both-funded cancellation.                      | Under-lock decision across all linked obligations; wrong-owner denial. |
| PF-06 / F2     | Claim/receipt/cancellation and refund/release in opposing schedules.                | Deterministic database barriers; rollback and conservation.            |
| PF-07 / F2     | Buyer confirm and auto-confirm before sufficient funding.                           | No fabricated cash, financial completion, commission or release.       |
| PF-08 / F2     | Canonical card verification on return, webhook-first and poll paths.                | No stored-success/client-only shortcut; real query proof.              |
| PF-09 / F2     | Both RFQ and direct booking; mounted outstanding-balance UI.                        | Entry-path, role, state and retry evidence; hosted browser later.      |
| PF-10 / F2     | Fresh replay and upgrade preserving pending/legacy evidence.                        | Execute functions/RLS; no fake receipts or historical rewrite.         |
| PF-11 / F3     | All pages, duplicate delivery, distinct same-reference movements.                   | No dropped movements; account-bound reconciliation.                    |
| PF-12 / F3     | Positive card/refund/payout missing, failed or skipped in drill.                    | Overall mandatory acceptance fails; no tautology.                      |
| PF-13 / F3     | Fee/settlement/opening funds and aged exceptions.                                   | Explicit bridge and unresolved reasons; no balancing plug.             |
| PF-14 / Review | Accepted 88 baseline plus new F1/F2/F3 cases.                                       | Exact source/schema, full identities and zero unexplained omissions.   |

Keep the six focused checkout repetitions distinct from the 88 unique baseline identities. Do not count source collection, SQL parse, mocked rows, cancelled runs or a protected gate that did not execute as acceptance. Preserve failed attempts as well as the final valid results.

## 12 | Legal, provider and release clearance

_EXTERNAL REVIEW REQUIRED; ENGINEERING CONTINUES_

### Regulatory review note as of 29 September 2026

The Bank of Zambia designation page consulted still describes the 2007 Act. The National Assembly also publishes the National Payment System Act No. 5 of 2026, whose subject matter includes licensing/authorization and replacement of the earlier statute. The available 2026 text makes commencement dependent on a statutory instrument; this review did not establish the applicable commencement instrument or transitional position. Do not assume either an older web page or a published Act alone answers Convergeo’s current authorization requirements. Obtain a current Zambian legal/provider determination before money activation. [R1, R2]

| Clearance                          | Required record                                                                                                                               |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Operating entity and custody model | Legal name/registration, party roles, permitted third-party collections/holds/payouts, applicable authorization/safeguarding decision.        |
| Consumer and merchant terms        | Remedies, cancellation deductions, notices, dispute/appeal process, category exceptions, acceptance and versioning. [R5, R6]                  |
| Account/rail authorization         | Sandbox and production account/key/origin binding, supported rails, webhook registration, platform/merchant rights.                           |
| Transfer response/retry semantics  | Actual account/destination echo, normalization, not-found variants, failed-reference reuse and reconciliation route. [R3]                     |
| Refund and card rules              | Permitted route by rail, consent/identity for any alternative, chargebacks, reversals, duplicate-recovery prevention.                         |
| Fees/settlement/reserves           | Merchant-specific schedule, minimum/maximum, gross/net/available positions and liquidity obligations; do not import unrelated provider terms. |
| Data and operations                | Registration, processing/hosting locations, transfers, retention/legal holds, operator roles, incident notifications. [R7, R8]                |

### Release authorization is a separate record

A policy approval does not authorize a Git merge, shared migration, provider transaction, scheduled-worker activation or production release. Require separately approved target/candidate identity, full real-stack and application evidence, provider-backed products/services/events results, recovery/rollback plan, staffing and exposure limits.

This research is focused drafting support, not a legal opinion or an exhaustive current-law review. Zambian counsel, the provider and the responsible financial/operator owners must confirm applicability and the remaining specifics. Controlled code/CI work can continue while that clearance is obtained.

## 13 | Sources and approval record

_PROVENANCE AND SIGN-OFF_

Source-derived requirements, code observations and new proposals are separate. No retrieved source supplied a complete signed financial policy. A handbook statement that one exists is not its text or its approval evidence.

| ID  | Source and use                                                                                                                            |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| S1  | F2-handoff(1).md / F2 continuation 29 September 2026: unpublished draft e792ad2a, proposal SQL, policy gaps and tests.                    |
| S2  | Convergeo_Lenco_Staging_Acceptance_2026-09-28.md: D1–D6, 24-case matrix and staged evidence boundaries.                                   |
| S3  | CONVERGEO_DELIVERY_HANDBOOK.md v1.0, 26 September 2026: owner decisions, cloud/no-restart controls and asserted existing reviewed policy. |
| S4  | GitHub #716 comment 5885685575: all-obligation ownership and forward migration reservations; not SQL approval.                            |
| S5  | docs/ops/lenco/lenco-api-distilled.md at accepted base: repository contract, not proof of a provider transaction.                         |
| R1  | Bank of Zambia: Designation of Payment Systems; page references the 2007 framework.                                                       |
| R2  | National Assembly: National Payment System Act No. 5 of 2026; commencement applicability remains to be confirmed.                         |
| R3  | Lenco API v2: GET /transfers/status/:reference, business statuses and response identity fields.                                           |
| R4  | Lenco API v2: Webhooks, event verification and supplementary re-query guidance.                                                           |
| R5  | National Assembly: Competition and Consumer Protection (Amendment) Act, 2023.                                                             |
| R6  | Zambia CCPC: official 12 October 2023 remedies/refunds report, used only as regulator context.                                            |
| R7  | Office of the Data Protection Commissioner: Data Protection Act source page.                                                              |
| R8  | Office of the Data Protection Commissioner: registration/FAQ guidance.                                                                    |

External references were checked on 29 September 2026. The accompanying Markdown source contains clickable references. This is not a statement that every applicable statute or provider account term was reviewed.

### Sign-off — all fields presently blank

Owner: __________________ Date: __________ Decision register version: __________
Legal reviewer: ___________ Date: __________ Scope/reference: _________________
Provider confirmation: _____________________ Scope/reference: _________________
Finance/accounting owner: _________________ Scope/reference: _________________
Engineering acceptance: ___________________ Candidate/evidence: ________________
Effective date and authorized target: __________________________________________

> Until a controlled approved revision exists, retain status DRAFT / NOT EFFECTIVE. Approval names, signatures, dates and clearances must never be generated or inferred by an agent.

## Reference links

- [S4] [GitHub ownership/allocation checkpoint](https://github.com/KaluMuso/Convergeo/issues/716#issuecomment-5885685575)
- [S5] [Canonical repository Lenco contract](https://github.com/KaluMuso/Convergeo/blob/8f78448e4b340787fae98eeee58c372cc5ded307/docs/ops/lenco/lenco-api-distilled.md)
- [R1] [Bank of Zambia designation guidance](https://www.boz.zm/payment-systems/designation-of-payment-systems)
- [R2] [National Assembly: National Payment System Act 2026](https://www.parliament.gov.zm/node/13028)
- [R2a] [2026 Act text and recorded commencement status (secondary legal publication)](https://zambialii.org/akn/zm/act/2026/5/eng%402026-04-08)
- [R3] [Lenco v2 transfer by reference](https://lenco-api.readme.io/v2.0/reference/get-transfer-by-reference)
- [R4] [Lenco v2 webhooks](https://lenco-api.readme.io/v2.0/reference/webhooks)
- [R5] [National Assembly: Competition and Consumer Protection amendment 2023](https://www.parliament.gov.zm/node/11544)
- [R6] [Zambia CCPC remedies report](https://ccpc.org.zm/details/85)
- [R7] [Data Protection Commissioner: Act](https://www.dataprotection.gov.zm/services/)
- [R8] [Data Protection Commissioner: FAQ](https://www.dataprotection.gov.zm/faq/)

These references are evidence inputs; follow-up legal/provider clearance is not implied.
