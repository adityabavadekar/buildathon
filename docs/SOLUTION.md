## 1. Requirements Breakdown

**Functional Requirements**

* **Webhook & Ingestion Handler:** Ingest payment failure events (e.g., failed subscription debits, checkout drop-offs, unpaid invoices) containing error sub-codes, timestamps, customer IDs, and transaction metadata.
* **Root Cause Classifier:** Map specific gateway error codes, downtime status, and past customer behaviors into a categorized failure type (e.g., transient network lag, structural auth failure, liquidity/insufficient funds).
* **Recovery case creation:** Every actionable revenue-loss event should become a Recovery Case.
* **Bounded Decision Engine:** Formulate recovery interventions (e.g., auto-reschedule, alternative payment link, customer outreach) subject to strict merchant rules.
* **Action Orchestrator (Tool Execution):** Dispatch the selected intervention (schedule a retry timestamp, generate a dynamic Razorpay payment link, or send an interactive messaging nudge).
* **Compliant Escalation & Stopping Mechanism:** Halt recovery workflows immediately upon reaching retry limits, customer opt-out, or low diagnosis confidence, routing the case to a human ops queue.
* **Audit Trail & Metrics Logger:** Persist an append-only log of every diagnostic trace, policy gate check, outreach cost, and recovery outcome.

**Non-Functional Requirements**

* **Strict Idempotency:** Prevent duplicate transactions, repeated customer notifications, or multi-charging under network retries or duplicate webhook delivery.
* **Deterministic Safety:** LLM reasoning must never bypass hard-coded safety constraints (zero hallucinated discounts, zero infinite loops).
* **Economic Viability:** Optimize for **Net Recovered Value (NRV)**:

$$\text{NRV} = \text{Recovered Revenue} - (\text{Retry Fees} + \text{Communication Costs} + \text{Discounts Offered})$$

* **Low Latency & Scalability:** Process incoming failure events asynchronously without blocking core checkout or subscription loops.

### Core operational capabilities

* **Live Agent Activity:** Stream real-time recovery events, decisions, policy checks, actions, and outcomes as they occur.
* **Workflow Progress:** Show each recovery case's current state, next action, waiting period, attempts, and expected completion.
* **Execution Logs:** Record every significant system, agent, policy, integration, and action event with timestamps.
* **Failure Visibility:** Surface failed API calls, agent errors, policy blocks, retries, timeouts, and workflow interruptions.
* **Automatic Failure Recovery:** Retry transient failures, resume interrupted workflows, and prevent duplicate financial actions.
* **Case Timeline:** Provide an end-to-end chronological history from revenue event through recovery or termination.
* **Agent Decision Trace:** Show what information influenced a decision, the selected action, confidence, and policy result.
* **System Health:** Show health/status of Razorpay integration, workers, AI service, event processing, and scheduled workflows.
* **Human Intervention Queue:** Surface cases where automation stopped, failed, or requires approval.
* **Audit Log:** Maintain an immutable-style record of financially relevant events and actions.

---

## 2. Feature Prioritization

| Layer | Feature | Scope & Purpose |
| --- | --- | --- |
| **Bare-Minimum Core (MVP)** | **Failure Classification** | Maps standard failure codes to clear recovery strategies. |
|  | **Deterministic Guardrails** | Hard boundaries for maximum 3 touches, minimum 24h cooldown, and discount caps. |
|  | **Multi-Rail Interventions** | Supports automated retries, smart payment link generation, and basic notification nudges. |
|  | **Audit Trail Logging** | Records reasonings, rule evaluations, timestamps, and status diffs. |
|  | **Batch Evaluation Harness** | Tests $\ge 50$ failure cases and benchmarks Net Recovered Value against naive retries. |
| **Add-On Features (Differentiators)** | **Hinglish/Voice Outreach** | Voice AI (e.g., Sarvam/ElevenLabs) calling for high-ticket overdue invoices. |
|  | **Promise-to-Pay (P2P) Tracker** | Natural-language date extraction from customer replies to pause dunning until agreed dates. |
|  | **Bank Health Monitor** | Ingests real-time issuer downtime signals to delay retries until bank success rates recover. |
|  | **Dynamic Margin Protection** | Algorithmic discount decay tied strictly to invoice aging and product profit margin. |

---

## 3. End-to-End System Flow

```
   [ Payment/Invoice Failure Event ]
                  │
                  ▼
   ┌───────────────────────────────┐
   │    1. INGESTION & DEDUPE      │ ──► Verify Idempotency Key (Drop if duplicate)
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │    2. CONTEXTUAL DIAGNOSIS    │ ──► Analyze failure code, user history, bank status
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │    3. POLICY & INVARIANT GATE │ ──► Check: Retries < 3? Cooldown active? Margin safe?
   └───────┬───────────────┬───────┘
           │ Passed        │ Breached / Low Confidence
           ▼               ▼
   ┌──────────────┐ ┌──────────────┐
   │  4. EXECUTE  │ │  5. ESCALATE │ ──► Queue to Merchant Ops Dashboard
   │ INTERVENTION │ └──────────────┘
   └───────┬──────┘
           │ (Schedule Retry / Send Smart Link / Nudge)
           ▼
   ┌───────────────────────────────┐
   │    6. STATE UPDATE & AUDIT    │ ──► Record decision trace, costs, and state change
   └───────────────────────────────┘

```

---

## Tech Stack

| Component                             | Technology                                   | Production Justification & Scalability Role                                                                                                                                                                |
| ------------------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Operator UI**                       | **Next.js 15 + React 19 + TypeScript**       | Production-grade operator console with Server Components, strong typing, and efficient rendering. Provides dashboards, recovery queues, case inspection, policy configuration, and live operational views. |
| **Realtime Updates**                  | **Server-Sent Events (SSE)**                 | Lightweight one-way streaming for live recovery progress, agent activity, workflow state changes, and system events without introducing unnecessary WebSocket complexity.                                  |
| **API / Control Plane**               | **Go + Fiber/Echo**                          | High-concurrency, low-overhead API and control-plane services. Horizontally scalable and well suited to webhook ingestion, case management, policy APIs, and high-volume service-to-service communication. |
| **Webhook Ingestion**                 | **FastAPI + Uvicorn**                        | High-throughput asynchronous webhook ingress with excellent Python ecosystem compatibility. Handles Razorpay event validation, normalization, and dispatch into the event backbone.                        |
| **Webhook Validation**                | **Rust validation service/library**          | Memory-safe, highly performant validation boundary for cryptographic signature verification and strict payload validation under high webhook bursts.                                                       |
| **Event Backbone**                    | **Apache Kafka**                             | Durable, partitioned event streaming with replay, consumer groups, replication, and horizontal scaling. Decouples Razorpay ingestion from recovery, analytics, notifications, audit, and ML consumers.     |
| **Workflow Orchestration**            | **Temporal.io**                              | Durable execution for multi-day recovery workflows. Provides persistent timers, retries, signals, workflow history, crash recovery, and exactly-once workflow semantics at the application level.          |
| **Agent Reasoning**                   | **LangGraph**                                | Explicit state-graph orchestration for bounded AI decision flows. Separates diagnosis, prioritization, planning, policy evaluation, and execution rather than relying on an unconstrained autonomous loop. |
| **Agent Checkpointing**               | **PostgresSaver / PostgreSQL**               | Durable checkpoint persistence for agent state and resumability across node executions and service failures.                                                                                               |
| **LLM Gateway**                       | **LiteLLM**                                  | Provider abstraction, model routing, fallbacks, token/cost tracking, and the ability to switch models without coupling the recovery engine to one provider.                                                |
| **Primary Database / Business State** | **PostgreSQL 16+**                           | ACID transactional source of truth for merchants, customers, recovery cases, policies, actions, approvals, workflow metadata, and financial state.                                                         |
| **Connection Pooling**                | **PgBouncer**                                | Protects PostgreSQL from connection exhaustion as API and worker instances scale horizontally.                                                                                                             |
| **Distributed Cache / Locks**         | **Redis / Dragonfly**                        | Low-latency caching, rate limiting, distributed coordination, short-lived locks, and idempotency protection around external actions.                                                                       |
| **Analytical Database**               | **ClickHouse**                               | High-performance OLAP engine for large-scale recovery analytics, intervention performance, cohort analysis, anomaly detection, and historical evaluation without burdening PostgreSQL.                     |
| **Search / Operations**               | **OpenSearch**                               | Fast full-text and faceted search across recovery cases, operational events, customer activity, and large audit datasets.                                                                                  |
| **Object Storage**                    | **S3-compatible storage**                    | Durable, inexpensive storage for raw webhook payloads, evaluation datasets, exported reports, model artifacts, and long-term archival data.                                                                |
| **Notification Service**              | **Dedicated Go service + provider adapters** | Isolates email/SMS/WhatsApp/voice delivery from the recovery engine and provides retries, rate limits, provider failover, and delivery tracking.                                                           |
| **Policy Engine**                     | **Dedicated deterministic service/library**  | Enforces retries, cooldowns, escalation thresholds, approval requirements, and contact limits independently of the LLM.                                                                                    |
| **Action Executor**                   | **Go service**                               | Executes financially relevant actions through Razorpay and other providers with idempotency, timeout handling, retries, and strict policy enforcement.                                                     |
| **Evaluation / Simulation**           | **Python**                                   | High-velocity environment for synthetic revenue scenarios, recovery simulations, baseline comparisons, statistical evaluation, and model experimentation.                                                  |
| **Observability**                     | **OpenTelemetry**                            | Unified distributed tracing, metrics, and telemetry across API → Kafka → Temporal → agent → policy → Razorpay → outcome.                                                                                   |
| **Metrics**                           | **Prometheus**                               | Production metrics for throughput, latency, workflow health, Kafka lag, recovery performance, API failures, and infrastructure health.                                                                     |
| **Dashboards**                        | **Grafana**                                  | Operational and engineering dashboards for system health, recovery KPIs, latency, failures, Kafka, Temporal, and infrastructure.                                                                           |
| **Distributed Tracing**               | **OpenTelemetry + Grafana Tempo**            | End-to-end traces connecting a single recovery case across distributed services and external API calls.                                                                                                    |
| **Centralized Logs**                  | **OpenTelemetry + Loki/OpenSearch**          | Structured, correlated application and workflow logs with searchable historical context.                                                                                                                   |
| **Error Tracking**                    | **Sentry**                                   | Application-level exception tracking, stack traces, release tracking, and frontend/backend error diagnostics.                                                                                              |
| **Containerization**                  | **Docker**                                   | Reproducible application packaging and consistent local, CI, staging, and production environments.                                                                                                         |
| **Container Orchestration**           | **Kubernetes**                               | Horizontal scaling, service discovery, rolling deployments, workload isolation, health checks, resource management, and multi-zone availability.                                                           |
| **Ingress / Gateway**                 | **Envoy / Cloud Load Balancer**              | TLS termination, routing, rate limiting, health checks, and controlled traffic distribution across services.                                                                                               |
| **Secrets Management**                | **Cloud Secrets Manager + KMS**              | Secure storage and rotation of Razorpay credentials, API keys, database credentials, and encryption keys.                                                                                                  |
| **Infrastructure as Code**            | **Terraform**                                | Reproducible infrastructure across development, staging, and production with reviewable infrastructure changes.                                                                                            |
| **CI**                                | **GitHub Actions**                           | Automated linting, unit/integration tests, security checks, builds, container publishing, and deployment pipelines.                                                                                        |
| **CD**                                | **Argo CD**                                  | GitOps-based Kubernetes deployments with declarative configuration, versioned releases, and automated reconciliation.                                                                                      |
| **Load Testing**                      | **k6**                                       | Reproducible load testing for webhook bursts, APIs, realtime streams, and recovery workloads.                                                                                                              |
| **Contract Testing**                  | **Pact / schema validation**                 | Protects service boundaries and external integration contracts as independently deployed services evolve.                                                                                                  |


### Defer — Production Hardening / Scale
Things NOT to work on right now unless 99% of project is done and implemented do not go on trying this!
- Kubernetes — Container orchestration and horizontal scaling.
- Terraform — Infrastructure-as-code.
- Argo CD — GitOps deployment.
- PgBouncer — PostgreSQL connection scaling.
- ClickHouse — Large-scale analytics/OLAP.
- OpenSearch — Large-scale operational search.
- S3 — Long-term raw-event/dataset archival.
- Rust webhook validator — Performance optimization after profiling.
- Envoy / production load balancer — Advanced ingress/routing.
- Cloud KMS + Secrets Manager — Production secret management.
- GitHub Actions — Full CI/CD pipeline.
- k6 — Load/performance testing.
- Pact / contract testing — Mature service-boundary testing.
- Chaos testing — Advanced resilience validation.
- Multi-region / disaster recovery — Later production rollout.

---

## 4. Phase-by-Phase SDLC Plan

1. **Phase 1: Domain Modeling & Policy Definition:** Requirements & State Modeling.
Map out all failure states (`FAILED`, `IN_DUNNING`, `P2P_PROMISED`, `RECOVERED`, `ESCALATED`, `ABANDONED`). Define the absolute policy boundaries (retry thresholds, discount caps, outreach channels) and the audit trail schema.


2. **Phase 2: Diagnostic & Intervention Layer:** Core Recovery Engine.
Implement the diagnosis logic to classify errors and output structured recovery plans. Integrate the policy gate to validate every plan deterministically before executing actions (mocking payment gateway calls and messaging APIs).


3. **Phase 3: Batch Simulation & Test Harness:** Validation & Edge Cases.
Build a synthetic batch of diverse failure scenarios (bank outages, insufficient funds, expired cards, hostile chargebacks). Run automated tests to verify stopping rules, error handling, and net economic recovery metrics.


4. **Phase 4: Dashboard & Audit Interface:** Observability & Presentation.
Create a clean operator interface showing aggregate batch recovery performance, cost breakdowns, and an inspectable chronological audit log for each processed transaction.

### 1. How State Works: Lifecycle & Timing

Dunning and revenue recovery is an **asynchronous, multi-day stateful workflow**, not a short-lived ephemeral request.

The state is **event-driven in real time, long-lived across days, and archived permanently for compliance.**

```
Event Ingest (Real-Time)
       │
       ▼
Active Dunning Window (2 to 7 Days)
├── State is mutable, persistent, and timer-driven
├── Waits for scheduled retries (e.g., +24h cooldown)
└── Waits for inbound user actions (e.g., webhook, WhatsApp reply)
       │
       ▼
Terminal Resolution (Permanent / Forever)
└── State becomes IMMUTABLE (RECOVERED / ESCALATED / WRITTEN_OFF)
└── Stored permanently in audit tables for accounting & model evaluation

```

* **Short-term / In-Flight (Minutes to Days):** When a payment fails, an active recovery record is created. It transitions across states (`FAILED` $\rightarrow$ `RETRY_SCHEDULED` $\rightarrow$ `OUTREACH_PENDING` $\rightarrow$ `P2P_WAITING`). It stays active until a terminal condition or hard timeout is met (typically 3 to 7 days).
* **Long-term / Permanent (Forever):** Once terminal, the record is locked. You never delete this data; it serves as your financial audit trail and training dataset for recovery efficacy.

---

### 3. Recommended Production-Grade Tech Stack

For a production-quality buildathon submission, prioritize **state persistence, delayed task scheduling, and strict locking**:

| Layer | Recommended Choice | Role & Justification |
| --- | --- | --- |
| **Database (State & Audit)** | **PostgreSQL** | • Relational integrity for transactions, invoices, and customers.<br>

<br>• JSONB support for raw webhook payloads and LLM reasoning traces.<br>

<br>• Row-level locking (`FOR UPDATE SKIP LOCKED`) for concurrency safety. |
| **Job Queue & Timers** | **Redis + BullMQ (Node/TS) OR Celery/ARQ (Python)** | • Handles scheduled delays (e.g., retry after 24h).<br>

<br>• Manages exponential backoff and retry scheduling out of the box. |
| **Workflow Engine (Optional Powerhouse)** | **Temporal.io** | • Best-in-class for long-running workflows (sleep for 3 days, wake up on webhook).<br>

<br>• Guarantees state preservation across system crashes. |
| **Backend API** | **FastAPI (Python) OR Fastify/NestJS (Node)** | • Fast webhook ingestion endpoints (`/webhooks/razorpay`).<br>

<br>• Async handlers for multi-channel dispatches. |
| **LLM & Agent Layer** | **LangGraph / LiteLLM / Direct API** | • Structured JSON schema validation.<br>

<br>• Deterministic tool calling for diagnosis. |
| **Dashboard / Observability** | **Next.js OR Streamlit** | • Live visual inspection of batch health, audit logs, and NRV metrics. |

---

### 4. How the Flow Operates Under the Hood

1. **Failure Occurs:** Razorpay sends a `payment.failed` webhook.
2. **Ingest & Lock:** Backend writes a record to PostgreSQL with status `ANALYSIS_QUEUED` using an idempotency key.
3. **Agent Diagnosis:** LLM evaluates error codes + customer history $\rightarrow$ proposes an action plan.
4. **Policy Check:** Hard guardrails validate the plan. If approved, the agent pushes a **delayed job** to Redis (e.g., *Schedule retry in 18 hours* or *Send WhatsApp link in 2 hours*).
5. **Worker Execution:** At timestamp $T$, the background worker wakes up, calls the Razorpay / WhatsApp tool, and logs the execution cost.
6. **State Resolution:**
* If a `payment.captured` webhook arrives $\rightarrow$ transition to `RECOVERED` $\rightarrow$ cancel pending dunning jobs.
* If max retries are exceeded $\rightarrow$ transition to `ESCALATED` $\rightarrow$ alert human ops.
