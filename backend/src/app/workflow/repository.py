"""Durable persistence repository for FORTX workflow instances and execution histories."""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.workflow.models import (
    WorkflowHistoryEvent,
    WorkflowInstance,
    WorkflowSignal,
    WorkflowStage,
    WorkflowStoppingRules,
    WorkflowTemplate,
    WorkflowTemplateDefinition,
)

logger = get_logger(__name__)


class WorkflowRepository:
    """Thread-safe ACID repository for durable workflow instances and event history."""

    def __init__(self, db_path: Path | str = "data/recovery_engine.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Create workflow tables and indexes if not already present."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    case_id TEXT UNIQUE NOT NULL,
                    template TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    recovery_state TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    stopping_rules_json TEXT NOT NULL,
                    timers_json TEXT NOT NULL,
                    attempts_count INTEGER NOT NULL DEFAULT 0,
                    touches_count INTEGER NOT NULL DEFAULT 0,
                    is_terminal INTEGER NOT NULL DEFAULT 0,
                    terminal_outcome TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_case ON workflows(case_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_stage ON workflows(current_stage);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflows_template ON workflows(template);"
            )

            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_events (
                    event_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    from_stage TEXT,
                    to_stage TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id)
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_events_wid ON workflow_events(workflow_id);"
            )

            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_signals (
                    signal_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id)
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_signals_wid ON workflow_signals(workflow_id);"
            )
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_template_definitions (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    base_template TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    allowed_actions_json TEXT NOT NULL,
                    stopping_rules_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            for column in ("graph_nodes_json", "graph_edges_json"):
                try:
                    cur.execute(
                        f"ALTER TABLE workflow_template_definitions ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]';"
                    )
                except sqlite3.OperationalError:
                    pass
            try:
                cur.execute(
                    "ALTER TABLE workflow_template_definitions ADD COLUMN description TEXT NOT NULL DEFAULT '';"
                )
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute(
                    "ALTER TABLE workflow_template_definitions ADD COLUMN status TEXT NOT NULL DEFAULT 'draft';"
                )
            except sqlite3.OperationalError:
                pass
            defaults = (
                (
                    "Failed payment recovery",
                    WorkflowTemplate.FAILED_PAYMENT,
                    "payment.failed",
                ),
                (
                    "Subscription renewal recovery",
                    WorkflowTemplate.SUBSCRIPTION_FAILURE,
                    "subscription.halted",
                ),
                (
                    "Overdue invoice collection",
                    WorkflowTemplate.OVERDUE_INVOICE,
                    "invoice.overdue",
                ),
                (
                    "Abandoned payment recovery",
                    WorkflowTemplate.ABANDONED_PAYMENT,
                    "checkout.abandoned",
                ),
                (
                    "Payment rail degradation",
                    WorkflowTemplate.PAYMENT_DEGRADATION,
                    "rail.degraded",
                ),
            )
            for name, base_template, trigger_type in defaults:
                template_id = f"builtin_{base_template.value.lower()}"
                now_iso = datetime.now(UTC).isoformat()
                cur.execute(
                    """INSERT OR IGNORE INTO workflow_template_definitions
                    (template_id, name, base_template, trigger_type, allowed_actions_json,
                     stopping_rules_json, graph_nodes_json, graph_edges_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        template_id,
                        name,
                        base_template.value,
                        trigger_type,
                        json.dumps(
                            ["diagnose", "retry", "notify", "payment_link", "escalate"]
                        ),
                        WorkflowStoppingRules().model_dump_json(),
                        json.dumps(
                            [
                                {
                                    "id": "trigger",
                                    "label": "Trigger",
                                    "type": "trigger",
                                },
                                {
                                    "id": "diagnose",
                                    "label": "Diagnose",
                                    "type": "decision",
                                },
                                {
                                    "id": "action",
                                    "label": "Bounded action",
                                    "type": "action",
                                },
                                {
                                    "id": "wait",
                                    "label": "Wait for signal",
                                    "type": "wait",
                                },
                            ]
                        ),
                        json.dumps(
                            [
                                {"source": "trigger", "target": "diagnose"},
                                {"source": "diagnose", "target": "action"},
                                {"source": "action", "target": "wait"},
                            ]
                        ),
                        now_iso,
                        now_iso,
                    ),
                )

    def save_workflow(self, instance: WorkflowInstance) -> None:
        """Upsert a workflow instance atomically."""
        with self._lock:
            cur = self._conn.cursor()
            now_iso = datetime.now(UTC).isoformat()
            cur.execute(
                """
                INSERT INTO workflows (
                    workflow_id, case_id, template, current_stage, recovery_state,
                    context_json, stopping_rules_json, timers_json, attempts_count,
                    touches_count, is_terminal, terminal_outcome, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    current_stage = excluded.current_stage,
                    recovery_state = excluded.recovery_state,
                    context_json = excluded.context_json,
                    stopping_rules_json = excluded.stopping_rules_json,
                    timers_json = excluded.timers_json,
                    attempts_count = excluded.attempts_count,
                    touches_count = excluded.touches_count,
                    is_terminal = excluded.is_terminal,
                    terminal_outcome = excluded.terminal_outcome,
                    updated_at = excluded.updated_at;
                """,
                (
                    instance.workflow_id,
                    instance.case_id,
                    instance.template.value,
                    instance.current_stage.value,
                    instance.recovery_state.value,
                    json.dumps(instance.context),
                    instance.stopping_rules.model_dump_json(),
                    json.dumps([t.model_dump(mode="json") for t in instance.timers]),
                    instance.attempts_count,
                    instance.touches_count,
                    1 if instance.is_terminal else 0,
                    instance.terminal_outcome,
                    instance.created_at.isoformat(),
                    now_iso,
                ),
            )

    def append_history(self, workflow_id: str, event: WorkflowHistoryEvent) -> None:
        """Append an execution history event to a workflow."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO workflow_events (
                    event_id, workflow_id, timestamp, from_stage, to_stage, event_name, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event.event_id,
                    workflow_id,
                    event.timestamp.isoformat(),
                    event.from_stage.value if event.from_stage else None,
                    event.to_stage.value,
                    event.event_name,
                    json.dumps(event.details),
                ),
            )

    def record_signal(self, workflow_id: str, signal: WorkflowSignal) -> None:
        """Record an incoming signal delivered to a workflow."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO workflow_signals (
                    signal_id, workflow_id, signal_type, payload_json, source, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    signal.signal_id,
                    workflow_id,
                    signal.signal_type.value,
                    json.dumps(signal.payload),
                    signal.source,
                    signal.timestamp.isoformat(),
                ),
            )

    def get_workflow(self, workflow_id: str) -> WorkflowInstance | None:
        """Fetch workflow instance with full history and signals."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?;", (workflow_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_instance(row)

    def get_workflow_by_case(self, case_id: str) -> WorkflowInstance | None:
        """Fetch workflow instance matching a specific case_id."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM workflows WHERE case_id = ?;", (case_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_instance(row)

    def list_workflows(
        self,
        limit: int = 50,
        stage: str | None = None,
        template: str | None = None,
    ) -> list[WorkflowInstance]:
        """List workflow instances with optional stage or template filter."""
        with self._lock:
            cur = self._conn.cursor()
            query = "SELECT * FROM workflows WHERE 1=1"
            params: list[Any] = []
            if stage:
                query += " AND current_stage = ?"
                params.append(stage)
            if template:
                query += " AND template = ?"
                params.append(template)
            query += " ORDER BY created_at DESC LIMIT ?;"
            params.append(limit)

            cur.execute(query, tuple(params))
            return [self._row_to_instance(r) for r in cur.fetchall()]

    def get_workflow_analytics(self) -> dict[str, Any]:
        """Return aggregate counts and status breakdowns for workflow observability."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT current_stage, COUNT(*) as count
                FROM workflows
                GROUP BY current_stage;
            """)
            stage_counts = {r["current_stage"]: r["count"] for r in cur.fetchall()}

            cur.execute("""
                SELECT template, COUNT(*) as count
                FROM workflows
                GROUP BY template;
            """)
            template_counts = {r["template"]: r["count"] for r in cur.fetchall()}

            cur.execute("SELECT COUNT(*) as total FROM workflows;")
            total = cur.fetchone()["total"]

            return {
                "total_workflows": total,
                "stage_counts": stage_counts,
                "template_counts": template_counts,
            }

    def list_template_definitions(self) -> list[WorkflowTemplateDefinition]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM workflow_template_definitions ORDER BY created_at DESC;"
            ).fetchall()
            return [self._row_to_template_definition(row) for row in rows]

    def get_template_definition(
        self, template_id: str
    ) -> WorkflowTemplateDefinition | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflow_template_definitions WHERE template_id = ?;",
                (template_id,),
            ).fetchone()
            return self._row_to_template_definition(row) if row else None

    def save_template_definition(
        self, definition: WorkflowTemplateDefinition
    ) -> WorkflowTemplateDefinition:
        with self._lock:
            now = datetime.now(UTC)
            definition.updated_at = now
            self._conn.execute(
                """INSERT INTO workflow_template_definitions
                (template_id, name, description, status, base_template, trigger_type, allowed_actions_json,
                 stopping_rules_json, graph_nodes_json, graph_edges_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id) DO UPDATE SET name=excluded.name,
                description=excluded.description,
                status=excluded.status,
                base_template=excluded.base_template, trigger_type=excluded.trigger_type,
                allowed_actions_json=excluded.allowed_actions_json,
                stopping_rules_json=excluded.stopping_rules_json,
                graph_nodes_json=excluded.graph_nodes_json,
                graph_edges_json=excluded.graph_edges_json, updated_at=excluded.updated_at;""",
                (
                    definition.template_id,
                    definition.name,
                    definition.description,
                    definition.status.value,
                    definition.base_template.value,
                    definition.trigger_type,
                    json.dumps(definition.allowed_actions),
                    definition.stopping_rules.model_dump_json(),
                    json.dumps(definition.graph_nodes),
                    json.dumps(definition.graph_edges),
                    definition.created_at.isoformat(),
                    now.isoformat(),
                ),
            )
            return definition

    def delete_template_definition(self, template_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM workflow_template_definitions WHERE template_id = ?;",
                (template_id,),
            )
            return cur.rowcount > 0

    @staticmethod
    def _row_to_template_definition(row: sqlite3.Row) -> WorkflowTemplateDefinition:
        graph_nodes = json.loads(row["graph_nodes_json"])
        graph_edges = json.loads(row["graph_edges_json"])
        # Older built-ins predate terminal nodes; normalize them on read.
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
        return WorkflowTemplateDefinition(
            template_id=row["template_id"],
            name=row["name"],
            description=row["description"]
            or f"Durable recovery path for {row['name'].lower()}.",
            status=row["status"],
            base_template=WorkflowTemplate(row["base_template"]),
            trigger_type=row["trigger_type"],
            allowed_actions=json.loads(row["allowed_actions_json"]),
            stopping_rules=json.loads(row["stopping_rules_json"]),
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_instance(self, row: sqlite3.Row) -> WorkflowInstance:
        """Convert a database row into a fully hydrated WorkflowInstance."""
        cur = self._conn.cursor()
        wid = row["workflow_id"]

        cur.execute(
            "SELECT * FROM workflow_events WHERE workflow_id = ? ORDER BY timestamp ASC;",
            (wid,),
        )
        events = [
            WorkflowHistoryEvent(
                event_id=e["event_id"],
                timestamp=datetime.fromisoformat(e["timestamp"]),
                from_stage=WorkflowStage(e["from_stage"]) if e["from_stage"] else None,
                to_stage=WorkflowStage(e["to_stage"]),
                event_name=e["event_name"],
                details=json.loads(e["details_json"]),
            )
            for e in cur.fetchall()
        ]

        cur.execute(
            "SELECT * FROM workflow_signals WHERE workflow_id = ? ORDER BY timestamp ASC;",
            (wid,),
        )
        signals = [
            WorkflowSignal(
                signal_id=s["signal_id"],
                signal_type=s["signal_type"],
                payload=json.loads(s["payload_json"]),
                source=s["source"],
                timestamp=datetime.fromisoformat(s["timestamp"]),
            )
            for s in cur.fetchall()
        ]

        return WorkflowInstance(
            workflow_id=row["workflow_id"],
            case_id=row["case_id"],
            template=WorkflowTemplate(row["template"]),
            current_stage=WorkflowStage(row["current_stage"]),
            recovery_state=row["recovery_state"],
            context=json.loads(row["context_json"]),
            stopping_rules=json.loads(row["stopping_rules_json"]),
            timers=json.loads(row["timers_json"]),
            signals_received=signals,
            history=events,
            attempts_count=row["attempts_count"],
            touches_count=row["touches_count"],
            is_terminal=bool(row["is_terminal"]),
            terminal_outcome=row["terminal_outcome"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


@functools.lru_cache(maxsize=1)
def get_workflow_repository() -> WorkflowRepository:
    """Return process-wide singleton workflow repository."""
    return WorkflowRepository()
