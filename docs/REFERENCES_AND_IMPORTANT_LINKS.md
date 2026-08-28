### 1. Official Documentation & Specifications

* **Razorpay Error Code Catalog & Sub-Codes:**
* [Razorpay Payment Error Codes & Reason Breakdown](https://razorpay.com/docs/errors/payments/list/): Direct mapping of payment errors (`bank_technical_error`, `bank_cutoff_in_progress`, `credit_limit_exceeded`, `funds_blocked_by_mandate`) and recommended mitigation steps.
* [Razorpay Generic API & HTTP 5XX Handling](https://razorpay.com/docs/errors/x/): Official idempotency retry schedules (intervals at 1 min, 2 min, 5 min) and `idempotency-key` lifecycle.
* [Razorpay Subscriptions & Autopay Webhook Specs](https://razorpay.com/docs/api/subscriptions/): Webhook schema specs for `subscription.charged`, `subscription.pending`, `subscription.halted`, and `payment.failed`.


* **NPCI UPI Autopay & e-NACH Technical Specifications:**
* [NPCI e-NACH & UPI Mandate Response Codes (Technical Spec)](https://docs.decentro.tech/reference/enach-mandate-registration-npci-error-codes): Detailed breakdown of NPCI-level failure codes (`AP09`, `AP10` mandate limit breaches, `AP15` balance insufficiency, `AP24` irregular account).
* [UPI Autopay & Collect Error Reference (Digio Reference)](https://documentation.digio.in/digicollect/upi/error_codes/): Issuer-level codes such as `K1` (risk decline), `VA`/`FL` (mandate paused/revoked), `XT`/`XU` (bank CBS cutoff in process), and `XY` (remitter CBS offline).


* **Checkout Recovery & Invoicing:**
* [Razorpay Magic Checkout Abandonment & Promotions API](https://razorpay.com/docs/developer-tools/integrations/magic-checkout/): Dynamic coupon application and checkout drop-off recovery hooks.
* [Razorpay Invoices & Payment Links API](https://razorpay.com/docs/api/payments/payment-links/): Dynamic creation of short-lived, single-use recovery links.



---

### 2. Reference Codebases & Official Repositories

* **Razorpay Official SDKs & Webhook Verification:**
* [Razorpay Node.js SDK (GitHub)](https://github.com/razorpay/razorpay-node): Official client for creating smart payment links, handling refunds, and parsing webhooks.
* [Razorpay Python SDK (GitHub)](https://github.com/razorpay/razorpay-python): Python client implementing HMAC-SHA256 signature verification for webhooks (`client.utility.verify_webhook_signature`).
* [Razorpay Webhook Signatures Guide](https://razorpay.com/docs/webhooks/validate-test/): Reference implementation for payload verification.


* **Open-Source State Machines & Dunning Implementations:**
* [Kill Bill (GitHub)](https://github.com/killbill/killbill): The industry-standard open-source subscription and dunning engine. Excellent architectural reference for retry overdue states and escalation matrices.
* [BullMQ (GitHub)](https://github.com/taskforcesh/bullmq): Production-grade Redis job scheduler supporting delayed execution, backoff strategies, and repeatable dunning timers.
* [Temporal Python SDK](https://github.com/temporalio/sdk-python) / [Temporal TypeScript SDK](https://github.com/temporalio/sdk-typescript): State-machine engine for modeling multi-day revenue recovery loops with persistent timers.



---

### 3. Industry Benchmarks & Technical Whitepapers

* **Payment Dunning Mechanics:** [Stripe Smart Retries Research](https://stripe.com/docs/billing/revenue-recovery/smart-retries) — Whitepaper detailing machine learning retries across issuer settlement windows (end-of-month liquidity vs. transient network drops).
* **RBI e-Mandate Directives:** [RBI Framework for Processing e-Mandates](https://www.google.com/search?q=https://www.rbi.org.in/Scripts/NotificationUser.aspx%3FId%3D11668) — Legal bounds on Pre-Debit Notifications (minimum 24-hour advance notice to customer before mandate execution) and maximum retry thresholds.

---

### 4. Technical Architecture Report

#### A. Gateway Error Taxonomy & Remediation Strategies

| Failure Code / NPCI Reason | Root Cause Category | Optimal Agent Intervention | Cooldown / Retry Constraint |
| --- | --- | --- | --- |
| `bank_cutoff_in_progress` / `XT`, `XU` | **Transient Banking Window** | Passive background auto-retry. No user notification needed. | Queue retry for $+4\text{ hours}$ (after typical midnight CBS cutoff). |
| `insufficient_funds` / `AP15`, `debit_declined` | **Liquidity Constraint** | Schedule retry for the 1st or 5th of the month (salary cycle) + send gentle WhatsApp reminder. | Max 2 retries; 48h minimum spacing. |
| `mandate_revoked` / `VA`, `FL` | **Structural Mandate Failure** | Abort auto-retry immediately. Dispatch single-use Razorpay Smart Payment Link. | Immediate failover to Card/UPI Intent. |
| `authentication_failed` / `OTP_TIMEOUT` | **Checkout Drop-Off** | Send interactive 1-click fallback link with dynamically calculated time-decay incentive. | 15-minute validity window. |

#### B. Algorithmic Metric for Batch Defense

To prove real financial performance in your Track 03 submission, calculate the **Net Recovered Value (NRV)** across your synthetic batch:

$$\text{NRV} = \sum_{i \in \text{Recovered}} \text{Amount}_i - \sum_{j \in \text{All}} \Big( N_{\text{retries}, j} \times C_{\text{gateway}} + N_{\text{outreach}, j} \times C_{\text{msg}} + \text{Discount}_j \Big)$$

Where:

* $C_{\text{gateway}} \approx ₹2.50$ (cost per failed/retried transaction)
* $C_{\text{msg}} \approx ₹0.50$ (cost per WhatsApp Business / SMS notification)
* $\text{Discount}_j$ = Concession granted to recover the payment

---

### 5. Essential JavaScript & API Integration Files to Inspect

If testing client-side checkout drop-offs or webhook listeners:

* **Razorpay Standard Checkout Script:** `[https://checkout.razorpay.com/v1/checkout.js](https://checkout.razorpay.com/v1/checkout.js)` (Inspect `modal.ondismiss` handlers to intercept manual drop-offs and emit drop-off events to your backend).
* **Payment Links API Endpoint:** `POST [https://api.razorpay.com/v1/payment_links](https://api.razorpay.com/v1/payment_links)` (Used by the agent's tool layer to generate fallback links).
* **Subscription Charge API Endpoint:** `POST [https://api.razorpay.com/v1/subscriptions/](https://api.razorpay.com/v1/subscriptions/){sub_id}/charge` (Used for executing scheduled mandate retries).
