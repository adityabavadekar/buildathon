# Research — Razorpay AI Buildathon

Compiled 2026-08-28. Status tags: **[V]** verified from primary source, **[T]** third-party
only, **[U]** unverified / could not resolve, **[X]** claim checked and found false.

---

## 1. Logistics

| Item | Finding | Status |
|---|---|---|
| Application deadline | September 5, 2026 | **[T]** aggregator blogs only; not on razorpay.com |
| Form status | Open, accepts responses; submission is one-shot | [V] |
| Applicant / slot counts | Not published | [U] |
| Prior edition | None found; no past winners to study | [U] |
| Weighted rubric | Not published, but four named criteria exist — see §7 | [V] |

Deliverables: public repo, ~5-min pitch video, architecture.
Offer: ₹75,000/month, 6 or 12 months, in-person Bangalore, starts September.

### De facto rubric
`razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/`
(2026-03-30) is the source of the tracks' "explainable, bounded and gated" language:
review-first mode, no irreversible action without explicit approval, double confirmation
for large transfers, platform validation layer (amount/PII/scope), per-action audit trail,
consent enforcement with permanent opt-out, ban on dark patterns (India 2023 Guidelines). [V]

### The tracks are Razorpay's own roadmap
`razorpay.com/agent-studio/` — merchant AI agent marketplace, stated on-page as built on
Anthropic's Claude Agent SDK. Shipping agents: Dispute Responder, Subscription Recovery,
Abandoned Cart Conversion, RTO Shield, RTO Insights, Settlement Insights, Cashflow
Forecaster. These map ~1:1 onto the five tracks. [V]

### Razorpay MCP server — fastest path to something real
`razorpay/razorpay-mcp-server` — official, Go, MIT, ~230 stars, actively pushed. **~45 tools**
(orders, payment links incl. UPI, refunds, QR codes, settlements, payouts, tokens,
`detect_stack`, `integrate_razorpay_checkout`). Hosted remote server at
**`https://mcp.razorpay.com/mcp`**, zero setup via `npx mcp-remote`, 401 unauthenticated,
**OAuth 2.0 + Dynamic Client Registration live**, PKCE S256. Docs confirm it
**auto-detects environment from the key — `rzp_test_` works.** [V]
Trap: the Feb 2026 "add agentic_integration tools" PR shipped checkout code-gen, not
agent-to-agent payments. [V]

### Engineering culture
`engineering.razorpay.com` 403s on page fetch; `/feed` serves full post bodies. Recent AI
posts are internal agent tooling: Hermes isolated per-employee agents (2026-07-12), AI
security triage 750h→2h (2026-06-09), Oncall Agent on LangGraph (2026-04-29), RCA-GPT
(2026-03-03). No posts on fraud ML, feature stores, or model serving. [V]
`razorpay.github.io/ai-playbook/` is public; its changelog repeatedly retracts unproven
claims — an evidence-and-receipts culture matching the tracks' demand for batch results. [V]

### Do not reference
- **"Razorpay Intelligence"** — does not exist, 404s. [X]
- **"Ray"** — only an "Ask RAY" Framer widget in homepage HTML; no product, docs, or
  press release. [X]
- **"NPCI UAP" / "UPI Agentic Protocol"** — the buildathon page uses this term; it appears
  in no source including NPCI's. See §4. [X]
- Razorpay is in **no** partner list for ACP, AP2, or x402 (checked agenticcommerce.dev,
  AP2 repo, ap2-protocol.org, x402.org). Juspay is the only Indian payments company in AP2.
  The buildathon page name-drops these as market context, not integrations. See §4a. [V]

---

## 4a. Agentic commerce protocols — do not implement one

The landscape consolidated; the "protocol war" framing is out of date.

| Protocol | Status | Reality for an 8-day build |
|---|---|---|
| **AP2** | **Donated to FIDO Alliance, 2026-04-28** | Spec + Python SDK, 3,160★, Apache-2.0. Payments TWG **co-chaired by Mastercard and Visa** — they are jointly standardizing AP2, not competing with it. Mastercard contributed "Verifiable Intent." **Spec's payment mandate examples include `"type": "UPI"`.** |
| **UCP** | Most active repo (3,338★) | ucp.dev — Google, Shopify, Etsy, Square, DoorDash, Hilton, Expedia. **Builds on AP2 for payments.** Transport-agnostic over REST/MCP/A2A. |
| **ACP** (OpenAI+Stripe) | SHIPPED, self-labeled **Beta** | Agentic Checkout (5 REST endpoints the *merchant* hosts) + Delegate Payment (PSP-hosted, single-use `vt_…` vault token with `allowance` capped by amount/expiry/merchant). Maintainers OpenAI/Stripe/**Meta**, founding maintainers retain veto. **No reference server, no SDK — only OpenAPI YAML.** Card/`fpan`-centric, no UPI handler. |
| **x402** | **Linux Foundation, 2026-07-14** | 6,551★, ~976K monthly npm downloads. Fastest possible demo (one middleware call). **But every shipped rail is on-chain — requires crypto/stablecoins.** Wrong fit for a fiat/UPI pitch. |
| **Visa Intelligent Commerce** | Real code (`visa/ai`, `visa/vic-reference-agent`) | Needs human-assigned token requestor + relationship ID. Not days. Only VIC AI partner verifiable from a Visa primary source is **OpenAI** (2026-06-10); the widely-repeated Anthropic/Microsoft/Perplexity/IBM/Samsung list **could not be verified**. |
| **Visa TAP** | Agent *identity* attestation only | RFC 9421 HTTP Message Signatures, not money movement. Runs locally with zero credentials, but **the repo has no spec** (gated behind onboarding) and Visa hasn't committed since Oct 2025 nor merged a single community PR. Parallel to Cloudflare Web Bot Auth. |
| **Mastercard Agent Pay** | **ANNOUNCED only** | All future tense, fully enterprise-gated. |

AP2 mandate mechanics, if cited: two types — **Checkout Mandate** and **Payment Mandate** —
as signed JWTs (`vct` claim, e.g. `mandate.payment.1`), cryptographically hash-bound to a
merchant-signed Checkout JWT. Five roles. [V]

**Implication:** none of these is buildable-and-differentiating in 8 days. AP2/UCP are
standards-body abstractions, ACP lacks a reference server, Visa/Mastercard are
credential-gated, x402 is crypto-only. Cite AP2's UPI credential type to show you know where
the rails are heading; don't implement it.

---

## 2. Razorpay test-mode API surface

Base URL is `https://api.razorpay.com/v1/` with test keys — no separate sandbox host.
Test mode is available immediately on signup; test/live keys are generated independently
of KYC. [V]

### Open (no activation gate documented)
Orders, Payments, Refunds, Customers, Payment Links, Payment Pages, Invoices, Tokens.
Recurring is explicit: "All recurring payments methods - Cards, UPI Autopay, Emandate and
Paper NACH, are available by default on your Razorpay account." [V]

### Gated
| API | Gate |
|---|---|
| **Route** | RBI PA rules (Sept 2025): domestic turnover > ₹40L (GST-3B) or export > ₹5L (FIRC). **Unavailable to a student.** |
| Smart Collect | Not available to `Individuals` MCC |
| QR Codes | Request via POC/Dashboard |
| Optimizer | Support request + third-party gateway creds |
| Magic Checkout | HubSpot form |
| Instant Settlements | Support request |
| Subscriptions | Needs Flash Checkout toggle (self-serve, not KYC) |
| S2S / raw card | PCI-DSS certification required |

### RazorpayX — open on signup, best test-mode ergonomics
Contacts, Fund Accounts, Payouts, Webhooks all work via API in test mode with a dummy
balance ("+ Add test balance"). Key demo feature: **you manually advance payout state from
the Dashboard** — "From the `processing` state, you will have to manually move the payout
to the next state... Unlike the Live Mode, this does not happen automatically." Test-mode
payout events: `payout.queued`, `payout.initiated`, `payout.processed`, `payout.reversed`,
`transaction.created`. Approval Workflow absent (no `pending`/`rejected`). Idempotency keys
mandatory since 2025-03-15; IP allowlisting required. [V]

### Reconciliation surface
`GET /v1/settlements/recon/combined?year=yyyy&month=mm` (+ `day`, `count`, `skip`).
SDK: `client.settlement.report({...})` (Python), `instance.settlements.settlementRecon({...})` (Node).
One row per settled transaction. Documented fields:

```
entity_id, type, debit, credit, amount, currency, fee, tax, on_hold, settled,
created_at, settled_at, settlement_id, posted_at, credit_type, description, notes,
payment_id, settlement_utr, order_id, order_receipt, method, card_network,
card_issuer, card_type, dispute_id
```

`type` ∈ {`payment`, `refund`, `transfer`, `adjustment`} — refunds/transfers as `debit`,
payments/adjustments as `credit`. Adjustment rows carry `description` and null
`settlement_utr`. [V]

Settlements entity (`GET /v1/settlements`) is thinner: `id`, `entity`, `amount`, `status`
(`created`/`processed`/`failed`), `fees`, `tax`, `utr`, `created_at`. Note: "In case of a
normal settlement the fee charge will be `0`" — fees/tax live on recon rows, not the header. [V]

**No `tds` field and no separate GST field exist** — `tax` is a single integer. [V]

Documented arithmetic: `settled = Payment - Adjustment - Tax - Fee - Transfer + Refunds` [V]

Bank-side identifiers in the Payments report schema: `Primary Transaction ID` (netbanking
`bank_transaction_id`, UPI `upi_transaction_id`, Cards/EMI ARN), `Retrieval Reference
Number` (RRN), `Auth Code`. [V]

Report generation appears Dashboard-only; no documented API to trigger or download. **[U]**

### Documented mismatch causes (exception taxonomy material)
- **Partial settlements** — when live balance < scheduled amount (e.g. a refund reduced it),
  Razorpay settles only transactions summing to available balance, defers the rest.
- **`processed` ≠ credited** — "does not mean that funds have been credited... can take up
  to **3 hours**."
- Settlements on hold (risk-flagged); failures from inactive/frozen/incorrect accounts.
- **Channel-segregated balances** (Online / In-Person / Alternate Payment Method
  International), each with its own schedule; reports add `Channel Type`, `Balance Account id`.
- **International FX** — converted at payment-creation rate, but dispute deductions use the
  dispute-day rate.
- Timing: domestic **T+2** working days from capture, excluding bank holidays. [V]

### THE OPEN RISK
Settlement docs require KYC approval and a fully activated account, and **nowhere document
test-mode settlement generation**. There is no test-mode settlement simulator (unlike Smart
Collect's "Make a Test Payment"), and `settlement.processed` is absent from RazorpayX's
test-mode event list. **Whether `/v1/settlements/recon/combined` returns non-empty data on
an unactivated test account is unresolved.** **[U]**

→ Day-1 action: call `GET /v1/settlements` and
`GET /v1/settlements/recon/combined?year=2026&month=08` with test keys before committing.

### Webhooks — fire in test mode
Separate URLs per mode. "Test events get triggered on a transaction done in the Test mode.
As the payload structure remains the same... you can rely on your stage testing."
Test-mode webhook setup/edit/delete requires default OTP `754081`. [V]

Signature: HMAC-SHA256 over the **raw** body in `X-Razorpay-Signature`
(`client.utility.verify_webhook_signature`). Dedupe on `x-razorpay-event-id`.
**Event ordering is not guaranteed** — `payment.authorized` may arrive after
`payment.captured`. [V]

`settlement.processed` is the only settlement event; there is no `settlement.failed` or
`settlement.created`. Dispute events: `payment.dispute.created/.won/.lost/.closed/
.under_review/.action_required`. [V]

**Blocker:** localhost unusable and the blacklist is aggressive — `webhook.site`,
`requestbin.com`, `ngrok.io`, `beeceptor.com`, `mockbin.org`, `hookbin.com`, `loca.lt`,
`localhost`, `.local` all rejected. Docs recommend **`zrok`**. Set up day 1. [V]

### Disputes — read + respond, cannot create
```
GET   /v1/disputes
GET   /v1/disputes/:id            (?expand[]=payment | ?expand[]=transaction.settlement)
POST  /v1/disputes/:id/accept
PATCH /v1/disputes/:id/contest
```
Evidence submission **is** API-accessible via `PATCH /contest` + Documents API (`doc_*`).
Evidence sub-fields: `amount`, `summary` (max 1000 chars), `shipping_proof`,
`billing_proof`, `cancellation_proof`, `customer_communication`, `proof_of_service`,
`explanation_letter`, `refund_confirmation`, `access_activity_log`,
`refund_cancellation_policy`, `term_and_conditions`, `others`, `submitted_at`.
Entity: `reason_code`, `reason_description`, `respond_by`, `amount_deducted`, `phase`, …
Statuses: `open`, `under_review`, `won`, `lost`, `closed`.
Phases: `fraud`, `retrieval`, `chargeback`, `pre_arbitration`, `arbitration`. [V]

No documented test-mode dispute simulation; plan for disputes to be empty and seed
fixtures. **[U]**

### Test-mode mechanics
**Cannot complete a payment API-only.** Test mode uses "a mock bank page with Success and
Failure buttons" — a browser step is required; the API-only path (S2S) needs PCI-DSS. An
automated harness needs a headless browser or fixtures. [V]

Success cards (any future expiry, any CVV): Visa `4111 1111 1111 1111`,
Mastercard `5267 3181 8797 5449`, RuPay `6073 8490 0000 0008`. OTP: 4–10 digits succeeds.
Forced failures have dedicated cards per reason — `payment_timed_out`,
`insufficient_funds`, `payment_cancelled`, `card_declined`,
`card_disabled_for_online_payments`, `card_number_invalid`, `gateway_technical_error`,
`authentication_failed`. [V]

**Watch out:** "In test mode, you can perform a subsequent debit only within 3 days of
token creation, as card tokens are valid for 3 days only." That bites mid-week in an
8-day build. [V]

Smart Collect has a Dashboard-only "Make a Test Payment" — clean way to fire
`virtual_account.credited`. [V]

Rate limits: documented qualitatively only (429 + backoff); **no published numeric limit**. [U]
SDKs: Python `razorpay` 2.0.1 (2026-03-09), Node `razorpay` 2.9.8 (2026-07-15). [V]

---

## 3. Datasets, benchmarks, and the LLM question

### Public fraud datasets
| Dataset | Rows | Real/synth | Fraud rate | Vintage | Friction |
|---|---|---|---|---|---|
| ULB Credit Card Fraud | **284,807** | Real (Worldline/ULB) | **0.1727%** (492) | 2013 data, pub. 2016 | None — plain curl, 150MB |
| IEEE-CIS | **590,540** train | Real (Vesta) | ~3.5% | 2019 | Kaggle account; HF mirrors exist |
| PaySim | **6,362,620** | Synthetic | 0.129% (8,213) | 2016 | None via HF |
| BankSim | [U] | Synthetic | [U] | ~2014 | Kaggle |
| Sparkov | [U] | Synthetic generator | [U] | 2019–20 | Kaggle |
| **Indian / UPI** | — | — | — | **None exists** — HF returns 0 | — |

Measured directly, not taken from blog lore:
- **ULB** spans exactly **48.00 hours** (max Time = 172,792s) and contains **1,081 exact
  duplicate rows** (19 among frauds). V1–V28 are PCA components → no feature engineering,
  no domain narrative. Stale and structurally unlike UPI. [V]
- **PaySim** `isFlaggedFraud` fires on only **16 of 8,213** frauds. Known balance-column
  leakage — anyone reporting 0.99 AUC is measuring leakage. [V]

Use **PR-AUC / average precision**, never accuracy or ROC-AUC, at 0.17% positives.

### LLM vs GBDT on tabular fraud — an LLM classifier loses
- **Grinsztajn et al.** (arXiv 2207.08815): trees remain SOTA on medium data across 45
  datasets and a **20,000 compute-hour** hyperparameter search, "even without accounting
  for their superior speed." NNs are hurt by uninformative features, lose data orientation,
  struggle with irregular functions — all characteristic of fraud data. [V]
- **TabLLM** (arXiv 2210.10723): competitive with GBDTs "especially in the very-few-shot
  setting" — the win is confined to tiny data. [V]
- **TabuLa-8B** (arXiv 2406.12031): beats XGBoost by 5–15pp only at **1–32 shots**. [V]
- TabLLM-style work benchmarked **Claude models directly and found them worse than any
  other baseline beyond 3 shots**. [V]
- **TabPFN-3** (arXiv 2605.13986, May 2026) scales to 1M rows and claims it beats 8-hour-
  tuned GBDTs. Caveats: the body shows the gap vs tuned XGBoost/CatBoost at 100k–1M rows is
  **not statistically significant** (parity), needs an H100, and is explicitly "**without
  using LLMs**" — a synthetic-prior transformer, not a language model. Not evidence for an
  LLM detector. [V]

At 285K–590K labeled rows you are in exactly the regime where the LLM advantage vanishes.
No published LLM-vs-XGBoost benchmark on ULB/IEEE-CIS specifically. [U]

### Production fraud pipelines
- **Stripe** (Sessions, 2025-05-07): prior models "gradually reduced card testing by **80%**
  over two years"; the Payments Foundation Model "increased its detection rate for attacks
  on large businesses by **64%** practically overnight," trained on "tens of billions of
  transactions." **Zero architecture detail published** — do not assert generative vs
  embedding. [V]
- **The "59%→97%" Stripe figure does not exist.** [X]
- **Feedzai RiskFM** is explicitly self-supervised, claiming only "parity with highly tuned
  bespoke models on Day 1" — the gain is deployment effort, not accuracy. That is the honest
  shape of foundation models in fraud: representation learning feeding classical
  classifiers. [V]
- Genuinely LLM-shaped in production: **Stripe Radar Assistant** (NL → fraud rules),
  **Forter MCP** (June 2026, Claude/ChatGPT for investigation and exec summaries),
  Ravelin NL querying. **Sift's dispute-response recommender is classical supervised
  learning, explicitly not generative.** [V]
- **Chargehound was acquired by PayPal, not Stripe**; responses are template-driven with no
  LLM. [X→V]

### Chargebacks
**Visa CE3.0** — effective **2023-04-15**, reason code **10.4 only**. Requires two prior
undisputed transactions **120–365 days** old, **either IP or device ID/fingerprint matching
across all three**, plus one additional match from IP / device ID / user ID / shipping
address. Liability shifts to issuer. Paths: pre-dispute via **Verifi Order Insight** (Visa
pre-selects up to five qualifying transactions; success also spares the VAMP ratio) or
post-chargeback via **VROL**. Datos Insights Q4 2024 (840 merchants): 93% of the 165 users
rated it effective. **No CE 4.0 exists.** [V]

→ **This is a deterministic date-and-field check, not a language task.** You can construct
cases that do and don't qualify and score exactly.

Mastercard's equivalent is **First-Party Trust** (Oct 2024, US-only). [V]
**Reason code 4899 does not exist**; Amex **"F14" does not exist** (Amex uses FR2 Full
Recourse, FR4 Immediate Chargeback). [X]

Recovery economics: **43.8% win rate on represented chargebacks, 10.7% net recovery**
(current Chargebacks911 Field Report). The widely-recycled **45%/18% is the superseded 2024
edition** — citing it would date you. Friendly-fraud share ranges 43.8%–86% depending on
vendor; the spread is the finding. The **$37.07B → $170.89B** figure is a manufactured
composite of two vendors' unrelated numbers — avoid. Analyst time per dispute: **not
found**; closest proxy is 23.5% of merchants using 5+ tools per dispute. [V]

**No public dispute dataset exists** — only 64-row reason-code glossary tables (zero
transactions) and self-described synthetic sets. CFPB is real and large but has no card
network, no reason code, no win/loss field. Primary rulebooks are gated (Visa Core Rules
behind Visa Online; Mastercard 403s automated access), so every figure above is
reconstructed from processor docs and vendors. [V]

India: **RBI/2019-20/67** (2019-09-20) mandates **₹100/day suo moto** compensation — bank
pays without a customer claim. **UDIR = "Unified Dispute and Issue Resolution"**, spanning
AePS/IMPS/UPI, not UPI-only. RuPay runs a separate NPCI chargeback framework. [V]
Unverified: whether Mastercard's own report contains the "75% first-party fraud" stat
attributed to it. [U]

### Reconciliation benchmarks — none exist
HuggingFace "reconciliation" returns **exactly 5 datasets** (two clinical-medication, one
hotel, one revenue model, one recent synthetic tool output) — **zero payment/bank
reconciliation benchmarks**. Kaggle bank-statement datasets are OCR/parsing tasks. Nearest
substitutes are entity-matching suites (WDC Products, Abt-Buy, Amazon-Google) which match
static product records by text similarity and model **no amounts, no balances, no
settlement lag** — structurally the wrong problem. arXiv rate-limited during the sweep, so
the literature side is "none found," not proven absent. [V/U]

→ **This void is the opportunity: a generator you write gives ground truth by
construction** — the most rigorously measurable option in the brief.

### Reconciliation — rules vs AI
Every serious vendor keeps the match decision **deterministic**. **BlackLine** (Aug 2026)
argues LLMs are structurally wrong for core matching: they "process numbers as text
strings, not true mathematical values," and non-reproducibility is "fundamentally
incompatible with SOX controls." Quotable: **"In corporate finance, a 95% accuracy rate is
a 100% operational failure."** Basware "Governed Autonomy," Puzzle's AI-drafts/human-signs-off,
Rillet's risk-tiered auto-posting all land on the same split. Sharpest datapoint: **Recko —
the Indian reconciliation startup Stripe acquired — has zero AI/ML language on its site**,
marketing purely on throughput and accuracy. Same for ClearTax GST reconciliation. [V]
(**Nominal could not be verified** — nominal.io is a hardware-testing company. Do not cite.) [X]

Legitimate split: deterministic engine does exact/tolerance/one-to-many matching; the LLM
sits **before** it (parsing unstructured remittances into structured fields) or **beside**
it (explaining breaks, drafting entries for human sign-off).

---

## 4. India regulatory constraints on agentic payments

`npci.org.in` is unreachable to automated access (React SPA shell, Akamai "Access Denied",
robots.txt and sitemap.xml 403). No NPCI circular could be read directly. All RBI items
below are primary-source verified.

### RBI Authentication Directions 2025 — the core constraint
**RBI/2025-26/79**, CO.DPSS.POLC.No. S 668/02-14-015/2025-2026, dated **2025-09-25**.
Compliance by **2026-04-01** (live now); cross-border by 2026-10-01. Minimum two distinct
factors, at least one **dynamic and unique to that transaction**; explicit risk-based
approach in para 8 (location/device/behavioural profile); SMS OTP not discontinued; issuer
must compensate the customer in full for losses from non-compliant transactions. [V]

**The agent-blocker, para 5 verbatim:** *"Authentication: Process of validating and
confirming the credentials of the customer who is originating the payment instruction."*
**An autonomous agent holds no such credential.** [V]

### RBI E-mandate Framework 2026
**RBI/DPSS/2026-27/396**, RBI/CO.DPSS.POLC.No.S56/02.14.003/2026-27, **2026-04-21**,
effective immediately. **Repealed all eight prior e-mandate circulars (2019–Aug 2024)** —
cite this one only. AFA-free up to **₹15,000/txn**; **₹1,00,000** for insurance premiums,
mutual fund subscriptions, credit card bills. Registration, modification, withdrawal and
first transaction all need AFA. 24-hour pre-debit notification with per-transaction opt-out
(the opt-out itself needs AFA), exempt only for FASTag/NCMC auto-replenishment. [V]

### UPI Reserve Pay (SBMD) — the legitimate bounded-spend primitive, but NOT activatable
Block funds once via UPI PIN, then debit multiple times with no further authentication;
query remaining limit, unblock unused, webhooks.
Razorpay docs: `razorpay.com/docs/payments/payment-gateway/s2s-integration/recurring-payments/upi-reserve-pay/`.
`razorpay.com/agentic-payments/` labels "Agentic Payments for In-App Commerce" **"Live in
Beta"**, with **UPI Reserve Pay "(Live)"** and UPI Circle "Coming soon." [V]

**BLOCKER: activation requires a support request, and supported apps are only BHIM,
INDMoney, and Karnataka Grameena Bank. Assume you cannot get this live for a buildathon —
model the envelope, do not promise a working SBMD block.** [V]

**Ceiling: max ₹10,000 per block, 90-day validity** (NPCI OC 228, 2025-10-08 — OCR-derived,
re-verify digits). That caps any agent spending envelope. [T]

NPCI-side attribution also rests on NPCI's own @NPCI_NPCI tweet of 2025-10-09 listing four
GFF 2025 features (UPI HELP on NPCI's own SLM, IoT Payments, Banking Connect, UPI Reserve
Pay). [T]
Independently corroborated by Cashfree and Pine Labs shipping the same primitive; Cashfree's
public docs resolve and are a fallback reference. [V]

### NPCI OC 201B — the closest thing to an official agent-mandate primitive
**2025-10-08.** Extends UPI Circle full delegation to IoT devices and software, **explicitly
naming "AI Profiles (initially for limited users in CUG)"**, purpose code 'BH', ₹15,000/month
and ₹5,000/txn caps. Constraint that matters: debits must be **"initiated by explicit user
action."** CUG pilot only. OCR-derived — **re-verify digits.** [T]

### UPI Circle / Delegated Payments — shipped but not student-accessible
UPI Circle OC 201, 2024-08-13; **tightened by OC 201A (July 2025) to family/employees with
KYC — so not student-accessible.** [T]
RBI announced Delegated Payments in the Statement on Developmental and Regulatory Policies,
**2024-08-08** (`prid=58449`). NPCI release 2024-08-13; launched 2024-08-19. Limits per NPCI
guidelines: full delegation ~₹5,000/txn and ~₹15,000/month; partial delegation = secondary
initiates, primary authenticates with UPI PIN; max 5 secondary users per primary; a
secondary may accept delegation from only one primary; 24-hour cooling period with
~₹5,000/day cap; app passcode/biometrics mandatory for secondary users. **No RBI circular
exists** — zero "delegat" hits across 2024–2025 notifications; this is NPCI-level operating
guidance only. [V/T]

### RBI FREE-AI Committee — shipped
Constituted **2024-12-26** (`prid=59377`, PR 2024-2025/1779). Chair: **Dr. Pushpak
Bhattacharyya**, IIT Bombay CSE. Members incl. Debjani Ghosh, Dr. Balaraman Ravindran
(IIT Madras), Abhishek Singh (MeitY), Rahul Matthan (Trilegal), Anjani Rathor (HDFC Bank),
Sree Hari Nagaralu (Microsoft India R&D); Member Secretary Suvendu Pati (CGM, FinTech Dept).
**Report published 2025-08-13** (`prid=61018`, PR 2025-2026/902): **7 Sutras** and **26
actionable recommendations** under six strategic pillars. Full PDF behind a captcha wall, so
verified to press-release level only. [V]

### Razorpay + NPCI + OpenAI pilot, and the Claude pilot
**2025-10-09** — explicitly built on **UPI Circle AND UPI Reserve Pay**. Axis Bank + Airtel
Payments Bank partners, BigBasket first merchant. NPCI ED Sohini Rajola on record. Harshil
Mathur quoted at length. **Pilot**, not GA. [V]

**2026-02-20, India AI Impact Summit — Razorpay + NPCI launched agentic payments on Claude**,
with Zomato / Swiggy / Zepto. Pilot, small user group. Mathur: *"the real challenge with
AI-led commerce isn't intelligence – it's trust."*
`razorpay.com/newsroom/razorpay-npci-launch-agentic-payments-on-claude-powering-zomato-swiggy-zepto-at-the-india-ai-impact-summit/` [V]

### Razorpay Agent Studio — read as the rubric
FTX'26, **2026-03-12**, "world's first," built on **Anthropic's Claude Agent SDK**. Launch
agents: Abandoned Cart Conversion, Dispute Responder, Subscription Recovery, Cashflow
Forecaster. Plus an Agentic Experience Platform (onboarding/dashboard/integration). Also
shipped: **Razorpay CLI** (2026-05-27) for Claude Cowork / OpenAI Codex, **RazorpayX AI
banking agents** (2026-06-01), UPI inside OpenAI Codex, Sarvam partnership for voice
commerce. [V]

**Razorpay's agentic strategy is UPI-native, not standards-native:** they are absent from the
AP2 60-org list, and `razorpay.com/docs/llms.txt` contains **zero** occurrences of "agentic,"
"ACP," "UCP," or "x402." [V]

### "NPCI Unified Agent Protocol" — press speculation, do not present as fact
Business Standard 2026-07-09 reports NPCI building a UAP to register/verify/authorise AI
agents across UPI without changing the rails, NPCI holding trust logs but not seeing what
was bought, launch "likely to require a regulatory nod from RBI." Based on **four anonymous
sources**; the article states an email to NPCI on July 2 went unanswered. No NPCI
confirmation anywhere. [T — treat as rumour]

### Negative finding worth using
Every RBI speech Jul–Aug 2026 was grepped, including both AI keynotes (Governor Malhotra
"Winning in the AI Era", FIBAC, 2026-08-11; DG S.C. Murmu "A Vision for Responsible AI",
2026-08-19) — **zero occurrences of "agentic"**. RBI's AI posture is model risk,
explainability, bias, and human oversight in credit, not agents spending money. Governor:
*"Preserve meaningful human oversight at every point where an AI system's error could cause
material harm"* and *"'The model decided' can never be an acceptable answer."* No RBI
sandbox cohort on AI/agentic payments. [V]

### CERT-In / MeitY BFSI Digital Threat Report 2025-26
`cert-in.org.in/PDF/Digital_Threat_Report_2025-26.pdf` (SISA + CERT-In + CSIRT-Fin, with a
Point of View by Secretary MeitY). Verified verbatim: **"Mandate human-in-the-loop controls
for agentic AI actions above defined financial thresholds, with full audit trails."** Also
*"Agentic AI operates with admin-level privilege under service-account-grade governance."* [V]

### Competing developer surface
**Cashfree** ships documented SBMD Reserve Pay + an MCP server at `mcp.cashfree.com` + an
Agent Toolkit for LangChain / Vercel AI SDK / OpenAI Agents SDK with explicit
`CFEnvironment.SANDBOX`. npm `@cashfreepayments/agent-toolkit` v1.1.0, published
2025-12-29, updated 2026-07-09. [V]

---

## 5. Local environment

Only **numpy** installed. No sklearn, xgboost, pandas, torch; no Kaggle CLI. Budget setup
time. Working search tooling was built at `/tmp/websearch.py` (DuckDuckGo Lite) and
`/tmp/fetch.py` (URL → text, `-g` regex filter); the WebSearch tool is unusable.

---

## 6. What this implies

**Measurable with ground truth you control:** reconciliation matching against a generator
seeded with Razorpay's documented pathologies (partial settlements, fee+tax netting,
duplicate UTRs, T+2 cutoffs, on-hold, `processed`-not-credited); CE3.0-style deterministic
eligibility logic; fraud PR-AUC on ULB/IEEE-CIS with a temporal split.

**Not measurable rigorously in 8 days:** dispute-letter quality (no dataset, no outcome
labels, LLM-judging your own cases is circular); "revenue recovered" in a simulation you
also wrote; any claim that an LLM beats tuned XGBoost on PR-AUC.

**Three independent signals — the per-track bars, the Agent Studio guardrails post, and the
ai-playbook's receipts culture — all say the measurement harness and audit trail are the
deliverable, and the agent itself is table stakes.**

### Highest-expected-value build
**Razorpay MCP server with `rzp_test_` keys as the agent's hands** (confirmed to work), wrapped
around a complete recovery loop that runs in test mode: **Magic Checkout abandoned-cart webhook
+ payment links**
(`razorpay.com/docs/build/llm-docs/payments/magic-checkout/abandoned-cart.md`).

Differentiate by **modeling the India consent layer** rather than implementing a protocol:
Reserve Pay-style blocks with the real ceilings (₹10,000/block, ₹5,000/txn, ₹15,000/month),
instant revocation, per-action audit trail, human confirmation step. Cite NPCI OC 201B's
"AI Profiles" clause, RBI Authentication Directions para 5, CERT-In's human-in-the-loop
mandate, and AP2's `"type": "UPI"` credential to show you know where the rails are heading.

**Do not promise autonomous agent-initiated debits.** NPCI's explicit-user-action clause and
India's AFA regime forbid it today, and Razorpay's own flagship is still a closed pilot.
Demonstrating the mandate/consent envelope with a human confirmation step reads as domain
knowledge; claiming full autonomy reads as a gap. This mirrors Mathur's own framing —
*"the real challenge with AI-led commerce isn't intelligence – it's trust."*

### Scope traps, consolidated
| Trap | Consequence |
|---|---|
| Route / marketplace split | RBI PA turnover gate — unavailable |
| UPI Circle delegation | OC 201A restricts to KYC'd family/employees |
| SBMD activation | Support request + only 3 supported apps |
| Payment completion API-only | Needs browser step or PCI-DSS |
| Webhook tunneling | ngrok/webhook.site blacklisted — use zrok |
| Card tokens in test mode | Expire after 3 days |
| LLM as tabular classifier | Contradicts the literature; loses to XGBoost |
| Dispute-letter generation | No ground truth; unscoreable |
| Implementing AP2/ACP/UCP | No reference server or credential-gated |
| x402 | Crypto-only rails |

---

## 7. Stated evaluation criteria

*"We read the work, not the resume. We look at how you think, build and solve problems."*

| Criterion | Stated as |
|---|---|
| **Problem taste** | did you pick something that actually matters |
| **Build quality** | does it run, is it structured, would you trust it |
| **AI judgment** | the right tool in the right place, **and where you chose not to use one** |
| **Failure recovery** | what broke, and what you did about it |

Three consequences that change the build:

1. **"Where you chose not to use one" is an explicit reward for abstaining from AI.** The
   BlackLine argument (LLMs "process numbers as text strings," non-reproducibility
   incompatible with SOX) and the LLM-vs-GBDT literature (§3) become scoreable assets, not
   caveats. A documented decision *not* to use an LLM on the matching/scoring path scores
   here, where in a normal hackathon it would read as under-ambition.
2. **"Failure recovery" must be a build artefact, not a story.** It wants what broke and what
   you did. Keep a decision log with reversals in it; the tracks' "one gracefully handled
   failure" requirement is the same idea. The `ai-playbook` changelog retracting its own
   unproven claims (§1) is the house style to imitate.
3. **"Would you trust it"** is a trust question, not a feature question — it aligns exactly
   with the Agent Studio guardrails post (§1) and CERT-In's human-in-the-loop mandate (§4).

### Track ranking against these criteria

| Rank | Track | Why |
|---|---|---|
| **1** | **Finance Controller** | Only track where the headline metric is arithmetic on ground truth you generate (§3: no benchmark exists). Deterministic matching + LLM confined to parsing/explanation is a textbook "chose not to use one." Weak spot: problem taste reads unglamorous — fix with the ₹-impact framing and Razorpay's real pathologies (§2). |
| **2** | **Agentic Commerce** | Highest ceiling on problem taste and trust: India consent layer, NPCI OC 201B "AI Profiles", RBI para 5, real MCP + OAuth. Highest variance — most crowded, and "grew revenue" is hard to measure honestly in 8 days. Rank 1 if backend/API strength. |
| **3** | **Risk Manager** | CE3.0 eligibility is deterministic and precisely scoreable (§3), and Disputes API closes a real loop (§2). But the fraud-detector framing is the most crowded choice and loses to XGBoost; a real dispute dataset does not exist. |
| **4** | **Revenue Recovery** | Self-grading: you simulate both the problem and the win. Only viable with a live abandoned-cart webhook loop in test mode — which is really the Agentic Commerce build. |
| **5** | **Open** | Forfeits a rubric that tells you exactly how to score, and starts with no credit for problem taste in Razorpay's domain. |
