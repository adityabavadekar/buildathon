# FORTX Workflow System Spec

Status: Spec only. Architecture decision approved by the merchant brief and
recorded in DECISIONS.md. Not yet implemented. A Temporal-based, durable,
long-running workflow is the target state for every recovery case. The current
in-process orchestrator plus SQLite jobs queue is the local persistence and
fallback; Temporal is the intended durable execution layer. An implementer must
fulfill this and run the End-to-End Verification Contract at the end, then
report the phrase "I have verified this completely end to end."

## Principles

- A FORTX workflow is the complete state machine for one revenue-recovery case:
  everything from detection to a terminal outcome.
- The workflow does NOT contain a giant continuously-running AI prompt. It is
  state plus context plus decision points plus policy gates plus actions plus
  waits plus events plus outcomes plus stopping rules.
- The Agent is one component inside the workflow, invoked at decision points when
  FORTX needs intelligence, never as a continuous loop.
- Safety layering: AI decides, Temporal executes durably, deterministic policy
  controls what is actually allowed. No layer can bypass the others.

## Durable workflow capabilities

- Durable workflows survive crash, retry, delay, and restart.
- Built-in workflow templates: failed payment, subscription failure, overdue
  invoice, abandoned payment, payment degradation.
- Dynamic agent decisions at decision points: the agent picks the next permitted
  strategy from context and prior outcomes.
- Deterministic policy gates: every agent-proposed action passes merchant policy
  before execution.
- Event-driven progression: Razorpay webhooks and other integration events wake
  or advance workflows instead of pure polling.
- Durable timers wait minutes/hours/days for retries, customer responses,
  promised payments, invoice due dates, cooldowns.
- Retry with bounded exponential backoff for transient integration failures,
  never a duplicate financial action.
- Replanning: after an unsuccessful intervention the workflow returns to the
  agent with the new outcome/context for the next strategy.
- Human escalation: pause/transition to human when confidence is low, value is
  high, policy requires approval, or automation is exhausted.
- Stopping rules: terminate on recovered, expired, max attempts, or prohibited.
- Workflow signals: external events (payment captured, invoice paid, customer
  response, subscription change) immediately alter a running workflow.
- Persisted state: stage, attempts, actions, timers, decisions, outcomes,
  ownership; every case resumable and inspectable.
- Versioning: evolve recovery strategies without corrupting running workflows.
- Idempotent execution of every financially consequential action.
- Observability: state, history, duration, pending action, failures, retries,
  outcome shown in the operator dashboard.
- Replay/debugging: complete execution history per case.
- Simulation: run against synthetic/historical cases without real financial
  action.
- Evaluation: compare strategies on recovery rate, incremental revenue,
  intervention count, customer contacts, escalation rate, time-to-recovery.
- Multi-provider: same logic over the provider abstraction (Razorpay, Stripe,
  PayPal, ...).
- Composable actions: retry, payment link, reminder, subscription recovery,
  receivables follow-up, escalation - without redesigning the engine.
- Campaign workflows: launch a recovery objective against a cohort; FORTX chooses
  the per-case strategy.
- Workflow analytics: active/waiting/recovering/recovered/failed/escalated/
  stopped counts and associated revenue.

## Inside one workflow

1. Trigger - the event that starts it (payment failure, invoice overdue,
   subscription failure, abandonment, ...).
2. Case Context - customer, payment, amount, provider, history, failure reason,
   previous attempts, merchant config, relevant events.
3. State - where the case is: detected, diagnosing, waiting, executing,
   recovering, escalated, recovered, stopped, ...
4. Decision Point - invoke the recovery agent with current context; ask for a
   bounded decision: what intervention, when, why.
5. Policy Check - validate the proposed action against merchant rules, limits,
   cooldowns, amount thresholds, contact limits, safety constraints.
6. Action - perform the approved intervention through an integration: retry
   payment, create payment link, send reminder, update subscription, escalate.
7. Timer/Wait - wait a defined period or external event without holding
   infrastructure.
8. Event Listener - receive payment captured, payment failed again, invoice
   paid, customer response, provider degradation, timeout.
9. Outcome Evaluation - succeeded, failed, still pending, or a new situation
   requiring another decision.
10. Replanning - on failure, provide the new state to the agent for another
    bounded strategy.
11. Attempt & Limit Tracking - track retries, interventions, communications,
    elapsed time, monetary exposure against stopping rules.
12. Human Handoff - transfer control when automation boundaries are crossed or
    approval is required.
13. Audit History - record every meaningful state transition, decision, policy
    result, action, event, outcome.
14. Terminal Condition - end as Recovered, Expired, Stopped, Escalated, or
    Unrecoverable.

Example failed-payment lifecycle:
Trigger -> Context -> Diagnose -> Agent decision -> Policy -> Retry -> Wait ->
Payment event -> Evaluate -> Agent decision -> Policy -> Payment Link -> Wait ->
Recovered -> Close.

## Relationship to existing code (verified on disk)

- `intervention/orchestrator.py` runs the agent and the case loop; keep its agent-
  invocation and decision-point logic as the decision layer.
- `intervention/policy_gate.py` is the deterministic gate; it must stay the single
  authority for what an action may do (do not duplicate gate logic in Temporal).
- `intervention/tools/` holds the composable actions; keep them as the Action layer
  the workflow calls through the provider abstraction.
- `audit/sqlite_store.py` jobs queue (`schedule_job`, `claim_next_due_job`,
  `reclaim_stuck_processing_jobs`, `update_job_status`) is today's local
  durability. Temporal is the durable execution layer; the SQLite queue can remain
  as deterministic fallback/local persistence or be superseded where Temporal
  provides equivalent durability. Decide at implementation, and record it.
- The 10% holdout arm, idempotency keys, and audit-before-action discipline must
  be preserved inside the workflow, not weakened.
- Add Temporal as a new engine layer (no `temporal` dependency exists yet).
  Provider calls still go through `llm/client.py` and payment tools only.

## End-to-End Verification Contract

1. A recovery case runs end to end as a durable workflow and survives a worker
   restart mid-exit without double action (idempotency + state check holds).
2. All four workflow templates exist (failed payment, subscription failure,
   overdue invoice, abandoned payment, + payment degradation) and pick the right
   lifecycle.
3. A decision point invokes the agent; the proposal must pass the deterministic
   policy gate before any action executes; a blocked proposal cannot run.
4. Razorpay payment webhooks wake/advance a running workflow promptly (event-driven,
   not pure polling) and act as signals.
5. Timers/cooldowns wait the configured period; a promised-payment workflow resumes
   from its wait on the promised date.
6. Replanning returns to the agent with updated outcome/context after failure and
   picks a bounded next strategy; stopping rules terminate on recovered/expired/
   max attempts.
7. Human escalation pauses/transitions a case and resumes after approval.
8. Workflow state and history persist and are fully replayable/debuggable per case;
   the operator dashboard shows current state, pending action, duration, retries,
   and outcome for each.
9. Simulation runs synthetic cases without real financial action; evaluation
   compares strategies using the holdout/counterfactual (no bypass in simulation
   mode).
10. Multi-provider abstraction and campaign-workflow launch work without redesigning
    the engine.

Report: state which of these you have verified completely end to end.
