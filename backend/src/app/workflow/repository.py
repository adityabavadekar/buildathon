"""Durable persistence repository for FORTX workflow instances and execution histories in PostgreSQL."""

from __future__ import annotations

import functools
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.core.db import get_db_connection
from app.core.enums import RecoveryState
from app.core.logging import get_logger
from app.workflow.models import (
    WorkflowAction,
    WorkflowHistoryEvent,
    WorkflowInstance,
    WorkflowSignal,
    WorkflowStage,
    WorkflowStoppingRules,
    WorkflowTemplate,
    WorkflowTemplateDefinition,
    WorkflowTimer,
    WorkflowTriggerType,
)

logger = get_logger(__name__)

BUILTIN_TEMPLATE_COUNT: int = 5


class WorkflowRepository:
    """Thread-safe ACID repository for durable workflow instances and event history in PostgreSQL."""

    def __init__(self, db_path: Any = None) -> None:
        self._lock = threading.RLock()
        self._seed_builtin_templates()

    def _seed_builtin_templates(self) -> None:
        """Ensure the 5 built-in workflow template definitions are seeded in PostgreSQL."""
        with self._lock:
            try:
                with get_db_connection() as conn:
                    # Clean out any old/invalid builtin definitions
                    conn.execute(
                        text(
                            "DELETE FROM workflow_template_definitions WHERE is_builtin = true"
                        )
                    )

                    now = datetime.now(UTC)
                    builtin_specs = [
                        (
                            "tpl_smart_dunning_v1",
                            "Smart Dunning & Escalation",
                            "Multi-channel dunning workflow with progressive messaging, smart wait windows, and human escalation.",
                            "published",
                            WorkflowTemplate.FAILED_PAYMENT.value,
                            WorkflowTriggerType.PAYMENT_FAILED.value,
                            [
                                WorkflowAction.DIAGNOSE.value,
                                WorkflowAction.RETRY.value,
                                WorkflowAction.NOTIFY.value,
                                WorkflowAction.PAYMENT_LINK.value,
                                WorkflowAction.ESCALATE.value,
                            ],
                            WorkflowStoppingRules(
                                max_retries=4,
                                max_touches=5,
                                max_duration_hours=72,
                                max_discount_bps=1000,
                            ).model_dump(mode="json"),
                            [
                                {
                                    "id": "trigger",
                                    "label": "Payment Failed",
                                    "type": "trigger",
                                },
                                {
                                    "id": "diagnose",
                                    "label": "Diagnose Rail & Customer",
                                    "type": "action",
                                },
                                {
                                    "id": "action",
                                    "label": "Execute Smart Outreach",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Wait for Settlement Window",
                                    "type": "wait",
                                },
                                {
                                    "id": "terminal",
                                    "label": "Complete",
                                    "type": "terminal",
                                },
                            ],
                            [
                                {"id": "e1", "source": "trigger", "target": "diagnose"},
                                {"id": "e2", "source": "diagnose", "target": "action"},
                                {"id": "e3", "source": "action", "target": "wait"},
                                {"id": "e4", "source": "wait", "target": "terminal"},
                            ],
                        ),
                        (
                            "tpl_payment_degradation_v1",
                            "Payment Rail Degradation Circuit Breaker",
                            "Durable hold and auto-reroute workflow when issuer bank or rail degradation is detected.",
                            "published",
                            WorkflowTemplate.PAYMENT_DEGRADATION.value,
                            WorkflowTriggerType.RAIL_DEGRADED.value,
                            [
                                WorkflowAction.DIAGNOSE.value,
                                WorkflowAction.RETRY.value,
                                WorkflowAction.PAYMENT_LINK.value,
                                WorkflowAction.ESCALATE.value,
                            ],
                            WorkflowStoppingRules(
                                max_retries=3,
                                max_touches=4,
                                max_duration_hours=24,
                                max_discount_bps=500,
                            ).model_dump(mode="json"),
                            [
                                {
                                    "id": "trigger",
                                    "label": "Rail Degraded",
                                    "type": "trigger",
                                },
                                {
                                    "id": "action",
                                    "label": "Hold & Fallback Switch",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Wait for Recovery",
                                    "type": "wait",
                                },
                                {
                                    "id": "terminal",
                                    "label": "Complete",
                                    "type": "terminal",
                                },
                            ],
                            [
                                {"id": "e1", "source": "trigger", "target": "action"},
                                {"id": "e2", "source": "action", "target": "wait"},
                                {"id": "e3", "source": "wait", "target": "terminal"},
                            ],
                        ),
                        (
                            "tpl_overdue_invoice_v1",
                            "B2B Overdue Invoice Smart Collect",
                            "Automated receivables collection creating virtual accounts with dynamic dunning cadence.",
                            "published",
                            WorkflowTemplate.OVERDUE_INVOICE.value,
                            WorkflowTriggerType.INVOICE_OVERDUE.value,
                            [
                                WorkflowAction.DIAGNOSE.value,
                                WorkflowAction.NOTIFY.value,
                                WorkflowAction.PAYMENT_LINK.value,
                                WorkflowAction.ESCALATE.value,
                            ],
                            WorkflowStoppingRules(
                                max_retries=5,
                                max_touches=6,
                                max_duration_hours=168,
                                max_discount_bps=1500,
                            ).model_dump(mode="json"),
                            [
                                {
                                    "id": "trigger",
                                    "label": "Invoice Overdue",
                                    "type": "trigger",
                                },
                                {
                                    "id": "action",
                                    "label": "Smart Collect Account",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Reconciliation Wait",
                                    "type": "wait",
                                },
                                {
                                    "id": "terminal",
                                    "label": "Complete",
                                    "type": "terminal",
                                },
                            ],
                            [
                                {"id": "e1", "source": "trigger", "target": "action"},
                                {"id": "e2", "source": "action", "target": "wait"},
                                {"id": "e3", "source": "wait", "target": "terminal"},
                            ],
                        ),
                        (
                            "tpl_mandate_expiry_v1",
                            "Recurring Mandate Pre-Debit & Renewal",
                            "Proactive auto-pay mandate health check, pre-debit reminder, and seamless update link.",
                            "published",
                            WorkflowTemplate.SUBSCRIPTION_FAILURE.value,
                            WorkflowTriggerType.SUBSCRIPTION_HALTED.value,
                            [
                                WorkflowAction.DIAGNOSE.value,
                                WorkflowAction.RETRY.value,
                                WorkflowAction.NOTIFY.value,
                                WorkflowAction.PAYMENT_LINK.value,
                            ],
                            WorkflowStoppingRules(
                                max_retries=3,
                                max_touches=4,
                                max_duration_hours=48,
                                max_discount_bps=0,
                            ).model_dump(mode="json"),
                            [
                                {
                                    "id": "trigger",
                                    "label": "Pre-Debit Window",
                                    "type": "trigger",
                                },
                                {
                                    "id": "action",
                                    "label": "Send Pre-Debit Notification",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Debit Execution Wait",
                                    "type": "wait",
                                },
                                {
                                    "id": "terminal",
                                    "label": "Complete",
                                    "type": "terminal",
                                },
                            ],
                            [
                                {"id": "e1", "source": "trigger", "target": "action"},
                                {"id": "e2", "source": "action", "target": "wait"},
                                {"id": "e3", "source": "wait", "target": "terminal"},
                            ],
                        ),
                        (
                            "tpl_checkout_abandonment_v1",
                            "Checkout Abandonment Intent Re-engagement",
                            "High-intent dropoff detection with timed nudge, dynamic concession, and single-click checkout.",
                            "published",
                            WorkflowTemplate.ABANDONED_PAYMENT.value,
                            WorkflowTriggerType.CHECKOUT_ABANDONED.value,
                            [
                                WorkflowAction.DIAGNOSE.value,
                                WorkflowAction.NOTIFY.value,
                                WorkflowAction.PAYMENT_LINK.value,
                            ],
                            WorkflowStoppingRules(
                                max_retries=2,
                                max_touches=3,
                                max_duration_hours=12,
                                max_discount_bps=500,
                            ).model_dump(mode="json"),
                            [
                                {
                                    "id": "trigger",
                                    "label": "Dropoff Detected",
                                    "type": "trigger",
                                },
                                {
                                    "id": "action",
                                    "label": "Issue Dynamic Nudge & Link",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Wait for Conversion",
                                    "type": "wait",
                                },
                                {
                                    "id": "terminal",
                                    "label": "Complete",
                                    "type": "terminal",
                                },
                            ],
                            [
                                {"id": "e1", "source": "trigger", "target": "action"},
                                {"id": "e2", "source": "action", "target": "wait"},
                                {"id": "e3", "source": "wait", "target": "terminal"},
                            ],
                        ),
                    ]

                    for spec in builtin_specs:
                        conn.execute(
                            text(
                                """
                                INSERT INTO workflow_template_definitions (
                                    template_id, name, description, status, base_template,
                                    trigger_type, allowed_actions_json, stopping_rules_json,
                                    graph_nodes_json, graph_edges_json, is_builtin, created_at, updated_at
                                ) VALUES (
                                    :tid, :name, :desc, :status, :btpl,
                                    :trig, CAST(:acts AS jsonb), CAST(:stop AS jsonb),
                                    CAST(:nodes AS jsonb), CAST(:edges AS jsonb), true, :cat, :uat
                                ) ON CONFLICT (template_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    description = EXCLUDED.description,
                                    status = EXCLUDED.status,
                                    base_template = EXCLUDED.base_template,
                                    trigger_type = EXCLUDED.trigger_type,
                                    allowed_actions_json = EXCLUDED.allowed_actions_json,
                                    stopping_rules_json = EXCLUDED.stopping_rules_json,
                                    graph_nodes_json = EXCLUDED.graph_nodes_json,
                                    graph_edges_json = EXCLUDED.graph_edges_json,
                                    updated_at = EXCLUDED.updated_at;
                                """
                            ),
                            {
                                "tid": spec[0],
                                "name": spec[1],
                                "desc": spec[2],
                                "status": spec[3],
                                "btpl": spec[4],
                                "trig": spec[5],
                                "acts": json.dumps(spec[6]),
                                "stop": json.dumps(spec[7]),
                                "nodes": json.dumps(spec[8]),
                                "edges": json.dumps(spec[9]),
                                "cat": now,
                                "uat": now,
                            },
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("workflow.seed_failed", error=str(exc))

    def save_workflow(self, workflow: WorkflowInstance) -> None:
        """Persist or update a workflow instance in PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workflows (
                        workflow_id, case_id, template, current_stage, recovery_state,
                        context_json, stopping_rules_json, timers_json, attempts_count,
                        touches_count, is_terminal, terminal_outcome, created_at, updated_at
                    ) VALUES (
                        :wid, :cid, :tpl, :stage, :state,
                        CAST(:ctx AS jsonb), CAST(:rules AS jsonb), CAST(:timers AS jsonb),
                        :attempts, :touches, :term, :out, :cat, :uat
                    ) ON CONFLICT (workflow_id) DO UPDATE SET
                        case_id = EXCLUDED.case_id,
                        template = EXCLUDED.template,
                        current_stage = EXCLUDED.current_stage,
                        recovery_state = EXCLUDED.recovery_state,
                        context_json = EXCLUDED.context_json,
                        stopping_rules_json = EXCLUDED.stopping_rules_json,
                        timers_json = EXCLUDED.timers_json,
                        attempts_count = EXCLUDED.attempts_count,
                        touches_count = EXCLUDED.touches_count,
                        is_terminal = EXCLUDED.is_terminal,
                        terminal_outcome = EXCLUDED.terminal_outcome,
                        updated_at = EXCLUDED.updated_at;
                    """
                ),
                {
                    "wid": workflow.workflow_id,
                    "cid": workflow.case_id,
                    "tpl": workflow.template.value
                    if hasattr(workflow.template, "value")
                    else str(workflow.template),
                    "stage": workflow.current_stage.value,
                    "state": workflow.recovery_state.value,
                    "ctx": json.dumps(workflow.context),
                    "rules": json.dumps(
                        workflow.stopping_rules.model_dump(mode="json")
                    ),
                    "timers": json.dumps(
                        [t.model_dump(mode="json") for t in workflow.timers]
                    ),
                    "attempts": workflow.attempts_count,
                    "touches": workflow.touches_count,
                    "term": workflow.is_terminal,
                    "out": workflow.terminal_outcome,
                    "cat": workflow.created_at,
                    "uat": workflow.updated_at,
                },
            )

    def append_history(self, workflow_id: str, event: WorkflowHistoryEvent) -> None:
        """Append an execution history event to a workflow in PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workflow_events (
                        event_id, workflow_id, timestamp, from_stage, to_stage, event_name, details_json
                    ) VALUES (
                        :eid, :wid, :ts, :f_stage, :t_stage, :ename, CAST(:details AS jsonb)
                    ) ON CONFLICT (event_id) DO NOTHING;
                    """
                ),
                {
                    "eid": event.event_id,
                    "wid": workflow_id,
                    "ts": event.timestamp,
                    "f_stage": event.from_stage.value if event.from_stage else None,
                    "t_stage": event.to_stage.value,
                    "ename": event.event_name,
                    "details": json.dumps(event.details),
                },
            )

    def record_signal(self, workflow_id: str, signal: WorkflowSignal) -> None:
        """Record an incoming signal delivered to a workflow in PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workflow_signals (
                        signal_id, workflow_id, signal_type, payload_json, source, timestamp
                    ) VALUES (
                        :sid, :wid, :stype, CAST(:payload AS jsonb), :src, :ts
                    ) ON CONFLICT (signal_id) DO NOTHING;
                    """
                ),
                {
                    "sid": signal.signal_id,
                    "wid": workflow_id,
                    "stype": signal.signal_type.value
                    if hasattr(signal.signal_type, "value")
                    else str(signal.signal_type),
                    "payload": json.dumps(signal.payload),
                    "src": signal.source,
                    "ts": signal.timestamp,
                },
            )

    def get_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        """Fetch workflow instance with full history and signals from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM workflows WHERE workflow_id = :wid"),
                    {"wid": workflow_id},
                )
                .mappings()
                .fetchone()
            )
            if not row:
                return None
            return self._row_to_instance(conn, row)

    def get_workflow_by_case(self, case_id: str) -> WorkflowInstance | None:
        """Fetch workflow instance matching a specific case_id from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM workflows WHERE case_id = :cid"),
                    {"cid": case_id},
                )
                .mappings()
                .fetchone()
            )
            if not row:
                return None
            return self._row_to_instance(conn, row)

    def list_active_workflows(self, limit: int = 50) -> list[WorkflowInstance]:
        """Fetch active (non-terminal) workflows from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM workflows WHERE is_terminal = false ORDER BY updated_at DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .mappings()
                .fetchall()
            )
            return [self._row_to_instance(conn, row) for row in rows]

    def list_workflows(
        self,
        *,
        stage: WorkflowStage | str | None = None,
        template: WorkflowTemplate | str | None = None,
        is_terminal: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowInstance]:
        """List workflows with optional filters and pagination from PostgreSQL."""
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if stage:
            clauses.append("current_stage = :stage")
            params["stage"] = (
                stage.value if isinstance(stage, WorkflowStage) else str(stage)
            )
        if template:
            clauses.append("template = :template")
            params["template"] = (
                template.value
                if isinstance(template, WorkflowTemplate)
                else str(template)
            )
        if is_terminal is not None:
            clauses.append("is_terminal = :is_term")
            params["is_term"] = is_terminal

        query = f"""
            SELECT * FROM workflows
            WHERE {" AND ".join(clauses)}
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset;
        """  # noqa: S608

        with self._lock, get_db_connection() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()
            return [self._row_to_instance(conn, row) for row in rows]

    def get_workflow_analytics(self) -> dict[str, Any]:
        """Return aggregate counts and status breakdowns for workflow observability from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            stage_rows = conn.execute(
                text(
                    "SELECT current_stage, COUNT(*) as count FROM workflows GROUP BY current_stage"
                )
            ).fetchall()
            stage_breakdown = {r[0]: int(r[1]) for r in stage_rows}

            tpl_rows = conn.execute(
                text(
                    "SELECT template, COUNT(*) as count FROM workflows GROUP BY template"
                )
            ).fetchall()
            template_breakdown = {r[0]: int(r[1]) for r in tpl_rows}

            tot = conn.execute(text("SELECT COUNT(*) FROM workflows")).scalar() or 0
            active = (
                conn.execute(
                    text("SELECT COUNT(*) FROM workflows WHERE is_terminal = false")
                ).scalar()
                or 0
            )
            recovered = (
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM workflows WHERE terminal_outcome = 'RECOVERED'"
                    )
                ).scalar()
                or 0
            )

            return {
                "total_workflows": int(tot),
                "active_workflows": int(active),
                "recovered_workflows": int(recovered),
                "recovery_rate": round(int(recovered) / int(tot), 4)
                if int(tot) > 0
                else 0.0,
                "stage_breakdown": stage_breakdown,
                "stage_counts": stage_breakdown,
                "template_breakdown": template_breakdown,
                "template_counts": template_breakdown,
            }

    def list_template_definitions(self) -> list[WorkflowTemplateDefinition]:
        """List all registered workflow templates definitions from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM workflow_template_definitions ORDER BY created_at DESC"
                    )
                )
                .mappings()
                .fetchall()
            )
            return [self._row_to_template_definition(row) for row in rows]

    def get_template_definition(
        self, template_id: str
    ) -> WorkflowTemplateDefinition | None:
        """Retrieve single workflow template definition by unique template_id."""
        with self._lock, get_db_connection() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM workflow_template_definitions WHERE template_id = :tid"
                    ),
                    {"tid": template_id},
                )
                .mappings()
                .fetchone()
            )
            if not row:
                return None
            return self._row_to_template_definition(row)

    def save_template_definition(
        self, template_def: WorkflowTemplateDefinition
    ) -> WorkflowTemplateDefinition:
        """Create or update merchant-authored workflow template definition in PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workflow_template_definitions (
                        template_id, name, description, status, base_template,
                        trigger_type, allowed_actions_json, stopping_rules_json,
                        graph_nodes_json, graph_edges_json, is_builtin, created_at, updated_at
                    ) VALUES (
                        :tid, :name, :desc, :status, :btpl,
                        :trig, CAST(:acts AS jsonb), CAST(:stop AS jsonb),
                        CAST(:nodes AS jsonb), CAST(:edges AS jsonb), false, :cat, :uat
                    ) ON CONFLICT (template_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        base_template = EXCLUDED.base_template,
                        trigger_type = EXCLUDED.trigger_type,
                        allowed_actions_json = EXCLUDED.allowed_actions_json,
                        stopping_rules_json = EXCLUDED.stopping_rules_json,
                        graph_nodes_json = EXCLUDED.graph_nodes_json,
                        graph_edges_json = EXCLUDED.graph_edges_json,
                        updated_at = EXCLUDED.updated_at;
                    """
                ),
                {
                    "tid": template_def.template_id,
                    "name": template_def.name,
                    "desc": template_def.description,
                    "status": template_def.status.value
                    if hasattr(template_def.status, "value")
                    else str(template_def.status),
                    "btpl": template_def.base_template.value
                    if hasattr(template_def.base_template, "value")
                    else str(template_def.base_template),
                    "trig": template_def.trigger_type.value
                    if hasattr(template_def.trigger_type, "value")
                    else str(template_def.trigger_type),
                    "acts": json.dumps(
                        [
                            a.value if hasattr(a, "value") else str(a)
                            for a in template_def.allowed_actions
                        ]
                    ),
                    "stop": json.dumps(
                        template_def.stopping_rules.model_dump(mode="json")
                    ),
                    "nodes": json.dumps(template_def.graph_nodes),
                    "edges": json.dumps(template_def.graph_edges),
                    "cat": template_def.created_at,
                    "uat": datetime.now(UTC),
                },
            )
            return template_def

    def delete_template_definition(self, template_id: str) -> bool:
        """Delete custom template definition if not built-in."""
        with self._lock, get_db_connection() as conn:
            res = conn.execute(
                text(
                    "DELETE FROM workflow_template_definitions WHERE template_id = :tid AND is_builtin = false"
                ),
                {"tid": template_id},
            )
            return res.rowcount > 0

    @staticmethod
    def _row_to_template_definition(row: Any) -> WorkflowTemplateDefinition:
        raw_nodes = row["graph_nodes_json"]
        graph_nodes = (
            raw_nodes if isinstance(raw_nodes, list) else json.loads(raw_nodes)
        )
        raw_edges = row["graph_edges_json"]
        graph_edges = (
            raw_edges if isinstance(raw_edges, list) else json.loads(raw_edges)
        )
        if graph_nodes and not any(
            node.get("type") == "terminal" for node in graph_nodes
        ):
            last_id = graph_nodes[-1].get("id", "last")
            graph_nodes.append(
                {"id": "terminal", "label": "Complete", "type": "terminal"}
            )
            graph_edges.append(
                {"id": "terminal-edge", "source": last_id, "target": "terminal"}
            )

        raw_actions = row["allowed_actions_json"]
        allowed_actions = (
            raw_actions if isinstance(raw_actions, list) else json.loads(raw_actions)
        )
        raw_stopping = row["stopping_rules_json"]
        stopping_rules = (
            raw_stopping if isinstance(raw_stopping, dict) else json.loads(raw_stopping)
        )

        c_at = row["created_at"]
        created_at = (
            c_at if isinstance(c_at, datetime) else datetime.fromisoformat(str(c_at))
        )
        u_at = row["updated_at"]
        updated_at = (
            u_at if isinstance(u_at, datetime) else datetime.fromisoformat(str(u_at))
        )

        return WorkflowTemplateDefinition(
            template_id=row["template_id"],
            name=row["name"],
            description=row["description"]
            or f"Durable recovery path for {row['name'].lower()}.",
            status=row["status"],
            base_template=WorkflowTemplate(row["base_template"]),
            trigger_type=row["trigger_type"],
            allowed_actions=[WorkflowAction(a) for a in allowed_actions],
            stopping_rules=WorkflowStoppingRules.model_validate(stopping_rules)
            if isinstance(stopping_rules, dict)
            else stopping_rules,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            created_at=created_at,
            updated_at=updated_at,
        )

    def _row_to_instance(self, conn: Any, row: Any) -> WorkflowInstance:
        """Convert a database row into a fully hydrated WorkflowInstance."""
        wid = row["workflow_id"]

        event_rows = (
            conn.execute(
                text(
                    "SELECT * FROM workflow_events WHERE workflow_id = :wid ORDER BY timestamp ASC"
                ),
                {"wid": wid},
            )
            .mappings()
            .fetchall()
        )

        history: list[WorkflowHistoryEvent] = []
        for er in event_rows:
            raw_details = er["details_json"]
            details = (
                raw_details
                if isinstance(raw_details, dict)
                else json.loads(raw_details)
            )
            ts = er["timestamp"]
            ts_dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))

            history.append(
                WorkflowHistoryEvent(
                    event_id=er["event_id"],
                    timestamp=ts_dt,
                    from_stage=WorkflowStage(er["from_stage"])
                    if er["from_stage"]
                    else None,
                    to_stage=WorkflowStage(er["to_stage"]),
                    event_name=er["event_name"],
                    details=details,
                )
            )

        signal_rows = (
            conn.execute(
                text(
                    "SELECT * FROM workflow_signals WHERE workflow_id = :wid ORDER BY timestamp ASC"
                ),
                {"wid": wid},
            )
            .mappings()
            .fetchall()
        )

        signals: list[WorkflowSignal] = []
        for sr in signal_rows:
            raw_payload = sr["payload_json"]
            payload = (
                raw_payload
                if isinstance(raw_payload, dict)
                else json.loads(raw_payload)
            )
            sts = sr["timestamp"]
            sts_dt = (
                sts if isinstance(sts, datetime) else datetime.fromisoformat(str(sts))
            )

            signals.append(
                WorkflowSignal(
                    signal_id=sr["signal_id"],
                    signal_type=sr["signal_type"],
                    payload=payload,
                    source=sr["source"],
                    timestamp=sts_dt,
                )
            )

        raw_context = row["context_json"]
        context = (
            raw_context if isinstance(raw_context, dict) else json.loads(raw_context)
        )
        raw_rules = row["stopping_rules_json"]
        stopping_rules = (
            raw_rules if isinstance(raw_rules, dict) else json.loads(raw_rules)
        )
        raw_timers = row["timers_json"]
        timers_data = (
            raw_timers if isinstance(raw_timers, list) else json.loads(raw_timers)
        )

        timers = [WorkflowTimer.model_validate(t) for t in timers_data]

        c_at = row["created_at"]
        created_at = (
            c_at if isinstance(c_at, datetime) else datetime.fromisoformat(str(c_at))
        )
        u_at = row["updated_at"]
        updated_at = (
            u_at if isinstance(u_at, datetime) else datetime.fromisoformat(str(u_at))
        )

        return WorkflowInstance(
            workflow_id=row["workflow_id"],
            case_id=row["case_id"],
            template=WorkflowTemplate(row["template"]),
            current_stage=WorkflowStage(row["current_stage"]),
            recovery_state=RecoveryState(row["recovery_state"]),
            context=context,
            stopping_rules=WorkflowStoppingRules.model_validate(stopping_rules)
            if isinstance(stopping_rules, dict)
            else stopping_rules,
            history=history,
            signals_received=signals,
            timers=timers,
            attempts_count=row["attempts_count"],
            touches_count=row["touches_count"],
            is_terminal=bool(row["is_terminal"]),
            terminal_outcome=row["terminal_outcome"],
            created_at=created_at,
            updated_at=updated_at,
        )


@functools.lru_cache(maxsize=1)
def get_workflow_repository() -> WorkflowRepository:
    """Return process-wide singleton WorkflowRepository instance."""
    return WorkflowRepository()
