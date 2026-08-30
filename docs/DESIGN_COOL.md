## UI Design Patterns

* **Floating tooltips** — Hover over unfamiliar icons, metrics, chart points, or truncated values to reveal concise contextual information.
* **Rich hover cards** — Hover a case, customer, or chart segment to preview key details without leaving the current page.
* **Command palette** — `⌘K` / `Ctrl+K` for instantly finding cases, customers, actions, pages, and filters.
* **Expandable rows** — Expand a recovery case directly inside a table for quick inspection without navigating away.
* **Slide-over drawers** — Use right-side drawers for case details, AI decisions, audit events, and configuration previews.
* **Sticky contextual header** — Keep case name, amount, status, and primary actions visible while scrolling through long details.
* **Breadcrumb navigation** — Clearly show context such as `Recovery → Active → RC-1842`.
* **Smart filters** — Filter chips with counts, multi-select, search, date ranges, and quick presets such as `High Risk` or `Needs Attention`.
* **Saved views** — Allow operators to save frequently used filtered recovery queues.
* **Interactive charts** — Hover for exact values, click segments to drill into underlying cases, and brush/select time ranges.
* **Chart cross-filtering** — Selecting a chart segment automatically filters related tables and metrics.
* **Animated live updates** — New recovery events subtly enter feeds/tables instead of abruptly changing the interface.
* **Live status indicators** — Small animated indicators for active workflows, connected integrations, and system health.
* **Inline status transitions** — Show `Retrying → Processing → Recovered` directly within case rows.
* **Skeleton loading** — Preserve page structure while data loads rather than showing generic spinners.
* **Optimistic interactions** — Immediately reflect safe UI changes while backend operations complete.
* **Toast notifications** — Compact confirmations for actions such as policy changes, approvals, or case reassignment.
* **Action confirmation sheets** — Use contextual confirmation for consequential financial actions rather than basic browser dialogs.
* **Undo actions** — Provide short undo windows for reversible operator actions.
* **Contextual action menus** — `•••` menus for secondary case operations without cluttering the main interface.
* **Keyboard shortcuts** — Fast navigation and case actions for frequent operators.
* **Command-driven filtering** — Allow natural combinations such as `overdue > 30d`, `amount > ₹1L`, `high risk`.
* **Number animations** — Subtle transitions when recovered revenue or case counts update in real time.
* **Sparkline metrics** — Tiny trend charts inside KPI cards to provide immediate historical context.
* **Comparison badges** — Show `↑ 12.4%`, `↓ 4 cases`, or `+₹2.8L vs baseline` beside major metrics.
* **Semantic status pills** — Compact, consistent labels for `Recovering`, `Waiting`, `Recovered`, `Escalated`, and `Failed`.
* **Severity indicators** — Combine icon + label + color instead of relying on color alone.
* **Timeline visualization** — Present recovery events chronologically with clear actors, timestamps, actions, and outcomes.
* **Decision cards** — Present AI recommendation, confidence, supporting signals, and policy result as a compact inspectable component.
* **Confidence visualization** — Use restrained progress bars/rings for recovery probability rather than flashy AI graphics.
* **Diff views** — When an agent changes a recovery plan, visually show `Previous strategy → New strategy` and why it changed.
* **Workflow stepper** — Compact horizontal progress indicator for `Detected → Diagnosed → Planned → Executing → Recovered`.
* **Status-aware UI** — Change available actions based on case state; don't show actions that cannot currently be performed.
* **Attention indicators** — Surface cases requiring human action without overwhelming the operator with alerts.
* **Activity grouping** — Group repetitive technical events while keeping the complete audit trail accessible.
* **Log expansion** — Keep technical logs collapsed by default; expand individual events for request/response metadata and traces.
* **Deep-linkable states** — Every case, filter, dashboard view, and audit event should have a stable URL.
* **Persistent filters** — Preserve filters when navigating into a case and returning to the queue.
* **Responsive tables** — Allow column prioritization/hiding rather than forcing users to horizontally scroll everything.
* **Virtualized lists** — Efficiently render very large recovery queues without degrading interaction performance.
* **Density controls** — Let operators choose comfortable or compact table density.
* **Hover highlighting** — Highlight the entire related row/series when hovering over a table row or chart element.
* **Focus mode** — Allow an operator to temporarily hide navigation/secondary panels while investigating a case.
* **Resizable panels** — Let users adjust the width of case information, activity, and analytics panels.
* **Split-view inspection** — Keep the recovery queue visible while inspecting a selected case.
* **Smart empty states** — Explain why there is no data and provide the next useful action.
* **Graceful error surfaces** — Show what failed, whether the system recovered automatically, and whether the operator needs to intervene.
* **Micro-interactions** — Small transitions for selection, expansion, completion, filtering, and state changes to make the UI feel polished.
* **Motion restraint** — Animate state changes and feedback, not ordinary navigation or every component.
* **Consistent iconography** — Use one icon system and consistent meanings throughout the application.
* **Layered information density** — KPI → summary → table → detail drawer → technical trace, so complexity appears only when needed.
* **Dark-mode technical views** — Keep the primary dashboard clean while allowing Agent Activity/Audit/Trace views to use a denser dark presentation.
* **Polished data visualization** — Prefer clean financial charts, restrained gradients, annotations, reference lines, and meaningful interactions over decorative 3D graphics.
* **Trust cues** — Clearly distinguish `AI recommended`, `Policy approved`, `Human approved`, and `Executed` so users know who/what made each decision.



High-value UI additions
Recovery Health Score — A single score for the merchant's recovery health, with the underlying factors available on hover.
Revenue-at-Risk heatmap — Calendar/time × payment method/provider showing where revenue leakage is concentrating.
Recovery opportunity map — Visualize cases by ₹ at risk × probability of recovery, immediately surfacing the highest-value opportunities.
"Money recovered today" live ticker — Subtle live counter that increases as the agent successfully recovers payments.
Recovery Pulse — A small live indicator: ₹42K recovered in the last 15 min · 7 cases.
AI opportunity banner — Occasionally surface high-value insights: ₹3.2L potentially recoverable from 47 cases.
Revenue waterfall — Total revenue → At risk → Recoverable → Attempted → Recovered → Lost, giving merchants an immediate leakage picture.
Recovery funnel drill-down — Clicking any funnel stage opens the exact cases contributing to that number.
"Why money is leaking" panel — Automatically surface the top 3 causes instead of forcing merchants to inspect charts.
Recovery opportunity ranking — Sort cases by expected recoverable value rather than simply amount or age.
Expected recovery value — Show ₹84K at risk · ₹65K expected recovery, combining amount and recovery probability.
AI recommendation badge — Small AI recommended indicator beside automated actions; hover explains the decision factors.
Policy badge — Auto-approved, Needs approval, or Blocked directly beside proposed actions.
Agent intervention preview — Before an action executes, show a compact preview such as Retry payment · Expected recovery ₹8,499 · Policy approved.
Live workflow animation — Cases subtly move through Detected → Diagnosed → Recovering → Recovered rather than relying only on static status labels.
Recovery streak — 23 consecutive successful recoveries can create a satisfying operational feedback loop.
"Recovered because of AI" metric — Specifically quantify revenue where the agent's intervention changed the outcome.
Baseline toggle — A simple switch between Actual and Baseline so merchants can immediately see incremental impact.
Counterfactual insight — Without intervention, estimated recovery: ₹42K · With agent: ₹68K.
System incident banner — If payment degradation is detected: Payment degradation detected · Recovery actions temporarily adjusted.
Merchant timeline — A unified view of important payment/recovery events for a customer.
Customer 360 popover — Hover a customer to see payment history, recovery attempts, lifetime value, and current cases without leaving the queue.
Quick actions on hover — Hover a case and reveal View · Approve · Pause · Escalate without cluttering the table.
Command palette — ⌘K for cases, customers, filters, policies, and actions.
Natural-language analytics — A small optional input: Why did recovery fall this week? → data-backed answer with links to relevant cases.
Saved operational views — High-value overdue, Failed twice, Needs human review, etc.
Personalized dashboard — Finance managers see money/KPIs; operators see active cases and actions.
Smart notification center — Only meaningful events: major degradation, unusually high revenue at risk, approval required, recovery milestone.
"Agent paused" control — Prominent global control to pause automated recovery actions while retaining monitoring.
Simulation mode — Let merchants test a policy/action against historical or synthetic cases before enabling it.
Policy impact preview — Changing Max retries: 2 → 3 immediately shows estimated additional recovery and additional customer contacts.
Recovery experiment cards — Strategy A recovered ₹4.2L · Strategy B ₹5.1L · +21%.
One-click case takeover — Human can instantly take ownership of an automated case.
Audit replay — Replay a case's timeline visually to understand exactly what happened.
Deep-link everything — Every case, filtered view, decision, and audit event should have a shareable URL.
One particularly cool idea

I'd add a "Recovery Opportunity Matrix" to the Overview:

                    HIGH RECOVERY PROBABILITY
                           ↑
                           │
             QUICK WINS    │    HIGH VALUE
                           │
                           │
 LOW VALUE ────────────────┼──────────────── HIGH VALUE
                           │
                           │
             LOW PRIORITY  │    HUMAN REVIEW
                           │
                           ↓
                    LOW RECOVERY PROBABILITY

Each bubble represents a recovery case, sized by ₹ at risk.


### Icons & Visual Assets

* **Use Lucide React** as the primary UI icon library for consistent, clean interface icons.
* **Use official brand assets** for Razorpay, UPI, WhatsApp, payment methods, etc.; don't recreate company logos.
* **Use Simple Icons** for technology/developer logos such as Kafka, PostgreSQL, Redis, Temporal, Kubernetes, Go, and Python.
* **Never generate or hand-draw SVG icons** — use established icon libraries or official assets instead.
* **Keep icons consistent** — same sizing/stroke style, semantic colors, and accessible labels/tooltips for unfamiliar or icon-only controls.

## UI / UX Product Principles

* **Every component is self-explanatory** — every metric, chart, status, control, and AI decision should have a concise description/tooltip explaining what it means, how it is calculated, or what happens when used; never rely on visual appearance alone.
* **Numbers-first analytics** — make payment/recovery analytics a first-class product: revenue at risk, recovered revenue, recovery rate, failure reasons, payment methods, retries, success rates, time-to-recovery, customer segments, intervention performance, trends, anomalies, baseline comparison, and incremental recovered revenue wherever data supports it.
* **Standard product conventions** — consistently provide copy buttons for IDs/values, external-link indicators, documentation links, “Learn more” links, breadcrumbs, searchable/filterable tables, deep links, pagination, export where useful, and clear in-app navigation.
* **Integration-native UX** — clearly show connected integrations, connection status, provider, last sync/event, available capabilities, errors, and configuration; use official provider logos/assets and make relevant resources/docs directly accessible.
* **Context + progressive disclosure** — show the important number/status/action immediately, then allow users to drill into definitions, methodology, case details, AI decisions, raw events, audit history, and technical information without overwhelming the primary dashboard.

### 1. Razorpay Design System (`Blade`) & Fintech-Specific Primitives

Razorpay uses its open-source design system called **Blade**. Mirroring its exact visual patterns signals strong domain alignment:

* **Blade Semantic Token Hierarchy:**
* *Surfaces:* `surface.background.level1` (app canvas), `surface.background.level2` (cards/elevations), `surface.border.subtle`.
* *Feedbacks:* `feedback.background.positive.subtle` (Emerald recovered), `feedback.background.notice.subtle` (Amber cooldowns), `feedback.background.negative.subtle` (Rose breaches).


* **India Payment Rail Chips:** Micro-badges displaying rail icons (`UPI-Autopay`, `e-NACH`, `Cards-TPV`, `NetBanking`) with sub-text indicators for bank status (e.g., `HDFC CBS Downtime ⚠️` or `SBI Mandate Limit`).
* **Razorpay Link Generator Preview:** An inline component rendering the real Razorpay payment link modal preview (`[api.razorpay.com/v1/payment_links](https://api.razorpay.com/v1/payment_links)`) with pre-applied decay discounts and dynamic UPI intent fallback buttons.
* **Pre-Debit Notice Compliance Flag:** Visual status tag for RBI compliance: `Pre-Debit Sent (T-24h) ✓` to verify that automatic debit execution adheres to mandate regulation.

### 2. High-Yield Bloomberg Terminal & Wall Street UI Principles

Large enterprise trading systems (Bloomberg, FactSet) rely on high data density and instant feedback:

* **Tufte "Data-Ink Ratio" Maximization:** Minimize non-functional padding and decorative gradients. Financial operators need high row density (28px–32px row heights) with clear monospaced numerical alignments (`font-mono`, tabular numbers `tnum`) for exact rupee values.
* **Color as State, Never Decoration:**
* **Green:** Capital locked/recovered (inflow).
* **Red:** Capital written off / human escalation breach.
* **Amber:** Scheduled delay / timer countdown in-flight.
* **Neutral Gray:** Suppressed / intentionally halted due to negative unit economics.


* **Temporal Micro-States (Countdown Clocks):** Inactive retries shouldn't just say `WAITING`. They should display live decrementing clocks (e.g., `Auto-Retry in 03:24:11` or `P2P Grace Period: 18h remaining`) to communicate that the background orchestrator is actively executing.
* **Keyboard Navigation Hotkeys (`Vim / Terminal Style`):**
* `J` / `K`: Move up/down rows in the active dunning table.
* `Space`: Open slide-over case drawer.
* `A`: Approve recommended intervention.
* `E`: Escalate to ops immediately.
* `P`: Pause automated dunning for the highlighted case.

### 3. Stripe & Enterprise Billing UI Principles

Stripe's billing and dunning interfaces excel at **transparency, counterfactual comparisons, and attribution**:

* **Revenue Attribution ("Smart Retries vs. Baseline"):** A visual attribution toggle allowing the merchant to view:
* *Total Recovered ($₹X$)*
* *Incremental AI Lift ($+₹Y$)* — revenue that would have failed permanently under a standard naive 3-day cron retry.


* **Dynamic Margin & Cost Ledger:** A collapsible mini-ledger on every transaction row:

$$\begin{aligned}     \text{Invoice Value:} &\quad +₹24,000.00 \\     \text{Gateway Retry Fee (2 attempts):} &\quad -₹5.00 \\     \text{WhatsApp API Template:} &\quad -₹0.50 \\     \text{Time-Decay Recovery Discount (2\%):} &\quad -₹480.00 \\     \hline     \mathbf{Net\ Contribution\ Margin:} &\quad \mathbf{+₹23,514.50}     \end{aligned}$$


* **"Why Action was Suppressed" Empty State:** If the agent chooses **not** to message or retry a customer, the drawer explicitly displays:
> *Action Suppressed: Negative Economic Expectation. (Expected Recovery ₹120 < Outreach Cost + Gateway Penalty ₹150).*


### 4. Advanced Operational Patterns to Add to Your Spec

* **Global Circuit Breaker (Panic Button):** A top-level status toggle that instantly switches the engine from `FULL_AUTONOMY` $\rightarrow$ `HUMAN_IN_THE_LOOP` $\rightarrow$ `MONITORING_ONLY` (pauses all outbound WhatsApp/retries while continuing to ingest webhooks).
* **Root-Cause Leakage Sunburst / Tree Map:** An interactive visual breakdown: `All Failures` $\rightarrow$ `Issuer Drop (64%)` $\rightarrow$ `HDFC CBS Cutoff (41%)` $\rightarrow$ `Recovered via T+4h Retry (98%)`.
* **Customer Communication Thread:** An interactive WhatsApp message preview box showing the exact AI-generated copy, customer's reply (e.g., *"Can I pay on the 5th after salary?"*), the agent's intent classification (`PROMISE_TO_PAY`), and the automatically updated timer.
