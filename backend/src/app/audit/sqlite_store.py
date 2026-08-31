"""ACID relational case storage engine with full query indexing, filtering, and model telemetry."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.audit.models import AuditEntry, ModelTelemetryEntry, RecoveryCase, ScheduledJob
from app.core.enums import AuditActor, ExperimentArm, JobStatus, RecoveryState
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(__name__)


class RelationalCaseStore:
    """Thread-safe ACID SQLite relational engine backing case records, audit trails, and jobs."""

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

    def _init_db(self) -> None:  # noqa: PLR0915
        """Initialize relational schema with indexes and migrations."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode = WAL;")
            cur.execute("PRAGMA synchronous = NORMAL;")

            # 1. Cases Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    payment_id TEXT UNIQUE NOT NULL,
                    merchant_id TEXT NOT NULL,
                    customer_id TEXT,
                    payment_rail TEXT,
                    error_code TEXT,
                    error_source TEXT,
                    state TEXT NOT NULL,
                    experiment_arm TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    touches_count INTEGER NOT NULL DEFAULT 0,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    outreach_count INTEGER NOT NULL DEFAULT 0,
                    discount_paise_granted INTEGER NOT NULL DEFAULT 0,
                    recovered_amount_paise INTEGER NOT NULL DEFAULT 0,
                    total_cost_paise INTEGER NOT NULL DEFAULT 0,
                    net_recovered_value_paise INTEGER NOT NULL DEFAULT 0,
                    is_opted_out INTEGER NOT NULL DEFAULT 0,
                    occurred_at TEXT,
                    invoice_id TEXT,
                    subscription_id TEXT,
                    experiment_tag TEXT,
                    due_at TEXT,
                    next_action TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # Schema migrations for existing databases
            for col, col_type in [
                ("customer_id", "TEXT"),
                ("payment_rail", "TEXT"),
                ("error_code", "TEXT"),
                ("error_source", "TEXT"),
                ("occurred_at", "TEXT"),
                ("invoice_id", "TEXT"),
                ("subscription_id", "TEXT"),
                ("campaign_id", "TEXT"),
                ("user_ref", "TEXT"),
                ("reference_id", "TEXT"),
                ("contact_email", "TEXT"),
                ("contact_phone", "TEXT"),
                ("experiment_tag", "TEXT"),
                ("virtual_account_id", "TEXT"),
                ("bank_transfer_id", "TEXT"),
                ("collected_amount_paise", "INTEGER"),
                ("collection_mode", "TEXT"),
                ("collected_at", "TEXT"),
                ("payment_link_id", "TEXT"),
                ("payment_link_url", "TEXT"),
                ("payment_link_expires_at", "TEXT"),
                ("strategy_tag", "TEXT"),
            ]:
                try:
                    cur.execute(f"ALTER TABLE cases ADD COLUMN {col} {col_type};")
                except sqlite3.OperationalError:
                    pass

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_merchant ON cases(merchant_id);"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_state ON cases(state);")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_arm ON cases(experiment_arm);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_rail ON cases(payment_rail);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_error ON cases(error_code);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_customer ON cases(customer_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_amount ON cases(amount_paise);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_created ON cases(created_at DESC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_exp_tag ON cases(experiment_tag);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_campaign ON cases(campaign_id);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_cases_user_ref ON cases(user_ref);"
            )

            # Lift legacy webhook notes into indexed columns while preserving raw data.
            cur.execute(
                "SELECT case_id, data_json FROM cases WHERE campaign_id IS NULL OR user_ref IS NULL OR reference_id IS NULL;"
            )
            for legacy_row in cur.fetchall():
                try:
                    raw_case = json.loads(legacy_row["data_json"])
                    event = raw_case.get("failure_event", {})
                    notes = event.get("metadata", {}).get("notes", {})
                    if not isinstance(notes, dict):
                        notes = {}
                    updates = {
                        "campaign_id": notes.get("campaign_id")
                        or notes.get("utm_campaign"),
                        "user_ref": notes.get("user_id")
                        or notes.get("customer_ref")
                        or notes.get("reference_id")
                        or notes.get("order_id"),
                        "reference_id": notes.get("reference_id"),
                        "contact_email": event.get("contact_email"),
                        "contact_phone": event.get("contact_phone"),
                    }
                    changed = False
                    for key, value in updates.items():
                        if (
                            value is not None
                            and not event.get(key)
                            and not raw_case.get(key)
                        ):
                            event[key] = value
                            raw_case[key] = value
                            changed = True
                    if changed:
                        cur.execute(
                            "UPDATE cases SET campaign_id = COALESCE(campaign_id, ?), user_ref = COALESCE(user_ref, ?), reference_id = COALESCE(reference_id, ?), contact_email = COALESCE(contact_email, ?), contact_phone = COALESCE(contact_phone, ?), data_json = ? WHERE case_id = ?;",
                            (
                                *updates.values(),
                                json.dumps(raw_case),
                                legacy_row["case_id"],
                            ),
                        )
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue

            # 2. Idempotency Key Index Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );
            """)

            # 3. Audit Trail Table (Append-only immutable)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit (
                    entry_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    reason TEXT,
                    notes TEXT,
                    decision_inputs TEXT,
                    decision_outputs TEXT,
                    model_metadata TEXT,
                    cost_incurred_paise INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_case ON audit(case_id, timestamp ASC);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_event ON audit(event_name);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp DESC);"
            )

            # 4. Scheduled Jobs Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    idempotency_key TEXT UNIQUE NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
                );
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status, due_at);"
            )

            # 5. Model Telemetry Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS model_telemetry (
                    id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    version TEXT,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0.0,
                    latency_ms REAL NOT NULL DEFAULT 0.0,
                    success INTEGER NOT NULL DEFAULT 1,
                    used_fallback INTEGER NOT NULL DEFAULT 0,
                    fallback_reason TEXT,
                    experiment_tag TEXT,
                    config_snapshot TEXT,
                    case_id TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            for col, col_type in [
                ("version", "TEXT"),
                ("fallback_reason", "TEXT"),
                ("experiment_tag", "TEXT"),
                ("config_snapshot", "TEXT"),
            ]:
                try:
                    cur.execute(
                        f"ALTER TABLE model_telemetry ADD COLUMN {col} {col_type};"
                    )
                except sqlite3.OperationalError:
                    pass

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_telemetry_model ON model_telemetry(model);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_telemetry_prov ON model_telemetry(provider);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_model_telemetry_exp ON model_telemetry(experiment_tag);"
            )
            self._conn.commit()

    def save_case(self, case: RecoveryCase, idempotency_key: str | None = None) -> None:
        """Atomically persist or update a recovery case, its audit entries, and idempotency key."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            try:
                data_json = case.model_dump_json()
                due_at_str = case.due_at.isoformat() if case.due_at else None
                created_str = case.created_at.isoformat()
                updated_str = case.updated_at.isoformat()
                rail_str = (
                    case.failure_event.payment_rail.value
                    if hasattr(case.failure_event.payment_rail, "value")
                    else str(case.failure_event.payment_rail)
                )
                occurred_str = case.failure_event.occurred_at.isoformat()
                exp_tag = getattr(case.failure_event, "experiment_tag", None)

                cur.execute(
                    """
                    INSERT INTO cases (
                        case_id, payment_id, merchant_id, customer_id, payment_rail,
                        error_code, error_source, state, experiment_arm,
                        amount_paise, currency, touches_count, retry_count, outreach_count,
                        discount_paise_granted, recovered_amount_paise, total_cost_paise,
                        net_recovered_value_paise, is_opted_out, occurred_at, invoice_id,
                        subscription_id, campaign_id, user_ref, reference_id,
                        contact_email, contact_phone, experiment_tag, due_at, next_action,
                        strategy_tag, virtual_account_id, bank_transfer_id,
                        collected_amount_paise, collection_mode, collected_at,
                        payment_link_id, payment_link_url, payment_link_expires_at,
                        version, data_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET
                        state = excluded.state,
                        touches_count = excluded.touches_count,
                        retry_count = excluded.retry_count,
                        outreach_count = excluded.outreach_count,
                        discount_paise_granted = excluded.discount_paise_granted,
                        recovered_amount_paise = excluded.recovered_amount_paise,
                        total_cost_paise = excluded.total_cost_paise,
                        net_recovered_value_paise = excluded.net_recovered_value_paise,
                        is_opted_out = excluded.is_opted_out,
                        due_at = excluded.due_at,
                        next_action = excluded.next_action,
                        strategy_tag = excluded.strategy_tag,
                        virtual_account_id = excluded.virtual_account_id,
                        bank_transfer_id = excluded.bank_transfer_id,
                        collected_amount_paise = excluded.collected_amount_paise,
                        collection_mode = excluded.collection_mode,
                        collected_at = excluded.collected_at,
                        payment_link_id = excluded.payment_link_id,
                        payment_link_url = excluded.payment_link_url,
                        payment_link_expires_at = excluded.payment_link_expires_at,
                        campaign_id = excluded.campaign_id,
                        user_ref = excluded.user_ref,
                        reference_id = excluded.reference_id,
                        contact_email = excluded.contact_email,
                        contact_phone = excluded.contact_phone,
                        version = cases.version + 1,
                        data_json = excluded.data_json,
                        updated_at = excluded.updated_at;
                    """,
                    (
                        case.case_id,
                        case.failure_event.payment_id,
                        case.merchant_id,
                        case.failure_event.customer_id,
                        rail_str,
                        case.failure_event.error_code,
                        case.failure_event.error_source,
                        case.state.value,
                        case.experiment_arm.value,
                        case.amount_paise,
                        case.currency,
                        case.touches_count,
                        case.retry_count,
                        case.outreach_count,
                        case.discount_paise_granted,
                        case.recovered_amount_paise,
                        case.total_cost_paise,
                        case.net_recovered_value_paise,
                        1 if case.is_opted_out else 0,
                        occurred_str,
                        case.failure_event.invoice_id,
                        case.failure_event.subscription_id,
                        case.campaign_id or case.failure_event.campaign_id,
                        case.user_ref or case.failure_event.user_ref,
                        case.reference_id or case.failure_event.reference_id,
                        case.contact_email or case.failure_event.contact_email,
                        case.contact_phone or case.failure_event.contact_phone,
                        exp_tag,
                        due_at_str,
                        case.next_action,
                        case.strategy_tag,
                        case.virtual_account_id,
                        case.bank_transfer_id,
                        case.collected_amount_paise,
                        case.collection_mode,
                        case.collected_at.isoformat() if case.collected_at else None,
                        case.payment_link_id,
                        case.payment_link_url,
                        case.payment_link_expires_at.isoformat()
                        if case.payment_link_expires_at
                        else None,
                        case.version,
                        data_json,
                        created_str,
                        updated_str,
                    ),
                )

                if idempotency_key:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO idempotency_keys (idempotency_key, case_id, created_at)
                        VALUES (?, ?, ?);
                        """,
                        (idempotency_key, case.case_id, updated_str),
                    )

                for entry in case.audit_trail:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO audit (
                            entry_id, case_id, event_name, actor, from_state, to_state,
                            reason, notes, decision_inputs, decision_outputs, model_metadata,
                            cost_incurred_paise, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            entry.entry_id,
                            entry.case_id,
                            entry.event_name,
                            entry.actor.value,
                            entry.from_state.value if entry.from_state else None,
                            entry.to_state.value if entry.to_state else None,
                            entry.reason if hasattr(entry, "reason") else None,
                            entry.notes,
                            json.dumps(entry.decision_inputs),
                            json.dumps(entry.decision_outputs),
                            json.dumps(entry.model_metadata)
                            if entry.model_metadata
                            else None,
                            entry.cost_incurred_paise,
                            entry.timestamp.isoformat(),
                        ),
                    )

                cur.execute("COMMIT;")
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def get_case(self, case_id: str) -> RecoveryCase | None:
        """Retrieve full recovery case including its audit trail."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT data_json FROM cases WHERE case_id = ?;", (case_id,))
            row = cur.fetchone()
            if not row:
                return None
            case = RecoveryCase.model_validate_json(row["data_json"])
            # Ensure audit trail from audit table is synced
            audit_rows = self.get_audit_trail_for_case(case_id)
            if audit_rows and len(audit_rows) > len(case.audit_trail):
                case.audit_trail = list(audit_rows)
            return case

    def get_case_by_payment_id(self, payment_id: str) -> RecoveryCase | None:
        """Retrieve recovery case by payment ID."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT case_id FROM cases WHERE payment_id = ?;", (payment_id,)
            )
            row = cur.fetchone()
            if not row:
                return None
            return self.get_case(row["case_id"])

    def get_case_by_idempotency_key(self, key: str) -> RecoveryCase | None:
        """Retrieve recovery case by registered idempotency key."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT c.case_id FROM cases c
                JOIN idempotency_keys k ON c.case_id = k.case_id
                WHERE k.idempotency_key = ?;
                """,
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self.get_case(row["case_id"])

    def _build_case_filter_query(  # noqa: PLR0912, PLR0915
        self,
        *,
        merchant_id: str | None = None,
        states: list[str] | None = None,
        experiment_arms: list[str] | None = None,
        payment_rails: list[str] | None = None,
        error_codes: list[str] | None = None,
        error_sources: list[str] | None = None,
        amount_min_paise: int | None = None,
        amount_max_paise: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        touches_min: int | None = None,
        touches_max: int | None = None,
        recovered: bool | None = None,
        opted_out: bool | None = None,
        has_escalation: bool | None = None,
        customer_id: str | None = None,
        payment_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        campaign_id: str | None = None,
        user_ref: str | None = None,
        reference_id: str | None = None,
        q: str | None = None,
        model_used: str | None = None,
    ) -> tuple[str, list[Any]]:
        """Build single reusable parameterized WHERE clause and parameters for search & count."""
        clauses: list[str] = []
        params: list[Any] = []

        if merchant_id:
            clauses.append("merchant_id = ?")
            params.append(merchant_id)

        if states:
            placeholders = ",".join("?" for _ in states)
            clauses.append(f"state IN ({placeholders})")
            params.extend(states)

        if experiment_arms:
            placeholders = ",".join("?" for _ in experiment_arms)
            clauses.append(f"experiment_arm IN ({placeholders})")
            params.extend(experiment_arms)

        if payment_rails:
            placeholders = ",".join("?" for _ in payment_rails)
            clauses.append(f"payment_rail IN ({placeholders})")
            params.extend(payment_rails)

        if error_codes:
            placeholders = ",".join("?" for _ in error_codes)
            clauses.append(f"error_code IN ({placeholders})")
            params.extend(error_codes)

        if error_sources:
            placeholders = ",".join("?" for _ in error_sources)
            clauses.append(f"error_source IN ({placeholders})")
            params.extend(error_sources)

        if amount_min_paise is not None:
            clauses.append("amount_paise >= ?")
            params.append(amount_min_paise)

        if amount_max_paise is not None:
            clauses.append("amount_paise <= ?")
            params.append(amount_max_paise)

        if created_after is not None:
            clauses.append("created_at >= ?")
            params.append(created_after.isoformat())

        if created_before is not None:
            clauses.append("created_at <= ?")
            params.append(created_before.isoformat())

        if occurred_after is not None:
            clauses.append("occurred_at >= ?")
            params.append(occurred_after.isoformat())

        if occurred_before is not None:
            clauses.append("occurred_at <= ?")
            params.append(occurred_before.isoformat())

        if touches_min is not None:
            clauses.append("touches_count >= ?")
            params.append(touches_min)

        if touches_max is not None:
            clauses.append("touches_count <= ?")
            params.append(touches_max)

        if recovered is not None:
            if recovered:
                clauses.append("recovered_amount_paise > 0")
            else:
                clauses.append("recovered_amount_paise = 0")

        if opted_out is not None:
            clauses.append("is_opted_out = ?")
            params.append(1 if opted_out else 0)

        if has_escalation is not None:
            if has_escalation:
                clauses.append(
                    "(state = 'ESCALATED' OR data_json LIKE '%case.escalated%')"
                )
            else:
                clauses.append("state != 'ESCALATED'")

        if customer_id:
            clauses.append("customer_id LIKE ?")
            params.append(f"{customer_id}%")

        if payment_id:
            clauses.append("payment_id LIKE ?")
            params.append(f"{payment_id}%")

        if invoice_id:
            clauses.append("invoice_id LIKE ?")
            params.append(f"{invoice_id}%")

        if subscription_id:
            clauses.append("subscription_id LIKE ?")
            params.append(f"{subscription_id}%")

        if campaign_id:
            clauses.append("campaign_id LIKE ?")
            params.append(f"{campaign_id}%")

        if user_ref:
            clauses.append("user_ref LIKE ?")
            params.append(f"{user_ref}%")

        if reference_id:
            clauses.append("reference_id LIKE ?")
            params.append(f"{reference_id}%")

        if q and q.strip():
            term = f"%{q.strip()}%"
            clauses.append(
                "(case_id LIKE ? OR payment_id LIKE ? OR customer_id LIKE ? OR error_code LIKE ? OR data_json LIKE ?)"
            )
            params.extend([term, term, term, term, term])

        if model_used and model_used.strip():
            clauses.append("data_json LIKE ?")
            params.append(f'%"model": "{model_used.strip()}"%')

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return where_str, params

    def list_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: list[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: list[str] | None = None,
        payment_rails: list[str] | None = None,
        error_codes: list[str] | None = None,
        error_sources: list[str] | None = None,
        amount_min_paise: int | None = None,
        amount_max_paise: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        touches_min: int | None = None,
        touches_max: int | None = None,
        recovered: bool | None = None,
        opted_out: bool | None = None,
        has_escalation: bool | None = None,
        customer_id: str | None = None,
        payment_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        campaign_id: str | None = None,
        user_ref: str | None = None,
        reference_id: str | None = None,
        q: str | None = None,
        model_used: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[RecoveryCase]:
        """List cases with server-side parameterized filtering, sorting, and pagination."""
        state_list = states or ([state.value] if state else None)
        arm_list = experiment_arms or (
            [experiment_arm.value] if experiment_arm else None
        )

        where_str, params = self._build_case_filter_query(
            merchant_id=merchant_id,
            states=state_list,
            experiment_arms=arm_list,
            payment_rails=payment_rails,
            error_codes=error_codes,
            error_sources=error_sources,
            amount_min_paise=amount_min_paise,
            amount_max_paise=amount_max_paise,
            created_after=created_after,
            created_before=created_before,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            touches_min=touches_min,
            touches_max=touches_max,
            recovered=recovered,
            opted_out=opted_out,
            has_escalation=has_escalation,
            customer_id=customer_id,
            payment_id=payment_id,
            invoice_id=invoice_id,
            subscription_id=subscription_id,
            campaign_id=campaign_id,
            user_ref=user_ref,
            reference_id=reference_id,
            q=q,
            model_used=model_used,
        )

        valid_sort_cols = {
            "created_at": "created_at",
            "updated_at": "updated_at",
            "amount_paise": "amount_paise",
            "recovered_amount_paise": "recovered_amount_paise",
            "touches_count": "touches_count",
            "due_at": "due_at",
        }
        col = valid_sort_cols.get(sort_by, "created_at")
        direction = "ASC" if sort_dir.lower() == "asc" else "DESC"

        query = f"SELECT data_json FROM cases {where_str} ORDER BY {col} {direction} LIMIT ? OFFSET ?;"  # noqa: S608
        params.extend([limit, offset])

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            return [RecoveryCase.model_validate_json(r["data_json"]) for r in rows]

    def count_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: list[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: list[str] | None = None,
        payment_rails: list[str] | None = None,
        error_codes: list[str] | None = None,
        error_sources: list[str] | None = None,
        amount_min_paise: int | None = None,
        amount_max_paise: int | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        occurred_after: datetime | None = None,
        occurred_before: datetime | None = None,
        touches_min: int | None = None,
        touches_max: int | None = None,
        recovered: bool | None = None,
        opted_out: bool | None = None,
        has_escalation: bool | None = None,
        customer_id: str | None = None,
        payment_id: str | None = None,
        invoice_id: str | None = None,
        subscription_id: str | None = None,
        campaign_id: str | None = None,
        user_ref: str | None = None,
        reference_id: str | None = None,
        q: str | None = None,
        model_used: str | None = None,
    ) -> int:
        """Count total matching cases using exact same predicate builder."""
        state_list = states or ([state.value] if state else None)
        arm_list = experiment_arms or (
            [experiment_arm.value] if experiment_arm else None
        )

        where_str, params = self._build_case_filter_query(
            merchant_id=merchant_id,
            states=state_list,
            experiment_arms=arm_list,
            payment_rails=payment_rails,
            error_codes=error_codes,
            error_sources=error_sources,
            amount_min_paise=amount_min_paise,
            amount_max_paise=amount_max_paise,
            created_after=created_after,
            created_before=created_before,
            occurred_after=occurred_after,
            occurred_before=occurred_before,
            touches_min=touches_min,
            touches_max=touches_max,
            recovered=recovered,
            opted_out=opted_out,
            has_escalation=has_escalation,
            customer_id=customer_id,
            payment_id=payment_id,
            invoice_id=invoice_id,
            subscription_id=subscription_id,
            campaign_id=campaign_id,
            user_ref=user_ref,
            reference_id=reference_id,
            q=q,
            model_used=model_used,
        )

        query = f"SELECT COUNT(*) as count FROM cases {where_str};"  # noqa: S608
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(query, params)
            row = cur.fetchone()
            return int(row["count"]) if row else 0

    def get_audit_trail_for_case(self, case_id: str) -> list[Any]:
        """Fetch immutable audit entries for a case."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT * FROM audit WHERE case_id = ? ORDER BY timestamp ASC;",
                (case_id,),
            )
            rows = cur.fetchall()
            entries: list[AuditEntry] = []
            for r in rows:
                entries.append(
                    AuditEntry(
                        entry_id=r["entry_id"],
                        case_id=r["case_id"],
                        event_name=r["event_name"],
                        actor=AuditActor(r["actor"]),
                        from_state=RecoveryState(r["from_state"])
                        if r["from_state"]
                        else None,
                        to_state=RecoveryState(r["to_state"])
                        if r["to_state"]
                        else None,
                        notes=r["notes"] or r["reason"],
                        decision_inputs=json.loads(r["decision_inputs"])
                        if r["decision_inputs"]
                        else {},
                        decision_outputs=json.loads(r["decision_outputs"])
                        if r["decision_outputs"]
                        else {},
                        model_metadata=json.loads(r["model_metadata"])
                        if r["model_metadata"]
                        else None,
                        cost_incurred_paise=r["cost_incurred_paise"],
                        timestamp=datetime.fromisoformat(r["timestamp"]),
                    )
                )
            return entries

    def schedule_job(self, job: ScheduledJob) -> None:
        """Schedule a background execution job with idempotency deduplication."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO jobs (
                    job_id, case_id, job_type, due_at, status,
                    idempotency_key, attempts, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    due_at = excluded.due_at,
                    status = excluded.status,
                    attempts = excluded.attempts,
                    updated_at = excluded.updated_at;
                """,
                (
                    job.job_id,
                    job.case_id,
                    job.job_type,
                    job.due_at.isoformat(),
                    job.status,
                    job.idempotency_key,
                    job.attempts,
                    json.dumps(job.payload),
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
            self._conn.commit()

    def fetch_due_jobs(self, limit: int = 20) -> list[ScheduledJob]:
        """Fetch pending jobs ready for execution whose due_at has passed."""
        now_str = datetime.now(UTC).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('QUEUED', 'PENDING') AND due_at <= ?
                ORDER BY due_at ASC LIMIT ?;
                """,
                (now_str, limit),
            )
            rows = cur.fetchall()
            jobs: list[ScheduledJob] = []
            for r in rows:
                jobs.append(
                    ScheduledJob(
                        job_id=r["job_id"],
                        case_id=r["case_id"],
                        job_type=r["job_type"],
                        due_at=datetime.fromisoformat(r["due_at"]),
                        status=r["status"],
                        idempotency_key=r["idempotency_key"],
                        attempts=r["attempts"],
                        payload=json.loads(r["payload"]),
                        created_at=datetime.fromisoformat(r["created_at"]),
                        updated_at=datetime.fromisoformat(r["updated_at"]),
                    )
                )
            return jobs

    def claim_next_due_job(self, now: datetime | None = None) -> ScheduledJob | None:
        """Atomically claim next due job in single transaction transitioning QUEUED -> PROCESSING."""
        now_val = now or datetime.now(UTC)
        now_str = now_val.isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN TRANSACTION;")
            try:
                cur.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status IN ('QUEUED', 'PENDING') AND due_at <= ?
                    ORDER BY due_at ASC LIMIT 1;
                    """,
                    (now_str,),
                )
                row = cur.fetchone()
                if not row:
                    cur.execute("COMMIT;")
                    return None

                job_id = row["job_id"]
                new_attempts = row["attempts"] + 1
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = 'PROCESSING', attempts = ?, updated_at = ?
                    WHERE job_id = ?;
                    """,
                    (new_attempts, now_str, job_id),
                )
                cur.execute("COMMIT;")
                return ScheduledJob(
                    job_id=row["job_id"],
                    case_id=row["case_id"],
                    job_type=row["job_type"],
                    due_at=datetime.fromisoformat(row["due_at"]),
                    status=JobStatus.PROCESSING.value,
                    idempotency_key=row["idempotency_key"],
                    attempts=new_attempts,
                    payload=json.loads(row["payload"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=now_val,
                )
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def reclaim_stuck_processing_jobs(self, max_processing_seconds: int = 60) -> int:
        """Reclaim orphaned jobs stuck in PROCESSING on worker crash."""
        cutoff = (
            datetime.now(UTC) - timedelta(seconds=max_processing_seconds)
        ).isoformat()
        now_str = datetime.now(UTC).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE jobs
                SET status = 'QUEUED', updated_at = ?
                WHERE status = 'PROCESSING' AND updated_at <= ?;
                """,
                (now_str, cutoff),
            )
            count = cur.rowcount
            self._conn.commit()
            return max(0, count)

    def update_job_status(
        self, job_id: str, status: str, attempts: int | None = None
    ) -> None:
        """Update job status and attempts."""
        now_str = datetime.now(UTC).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            if attempts is not None:
                cur.execute(
                    "UPDATE jobs SET status = ?, attempts = ?, updated_at = ? WHERE job_id = ?;",
                    (status, attempts, now_str, job_id),
                )
            else:
                cur.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?;",
                    (status, now_str, job_id),
                )
            self._conn.commit()

    def record_model_telemetry(self, telemetry: ModelTelemetryEntry) -> None:
        """Record model invocation telemetry directly to model_telemetry table."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO model_telemetry (
                    id, model, provider, version, input_tokens, output_tokens,
                    cost_usd, latency_ms, success, used_fallback, fallback_reason,
                    experiment_tag, config_snapshot, case_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    telemetry.id,
                    telemetry.model,
                    telemetry.provider,
                    telemetry.version,
                    telemetry.input_tokens,
                    telemetry.output_tokens,
                    telemetry.cost_usd,
                    telemetry.latency_ms,
                    1 if telemetry.success else 0,
                    1 if telemetry.used_fallback else 0,
                    telemetry.fallback_reason,
                    telemetry.experiment_tag,
                    json.dumps(telemetry.config_snapshot)
                    if telemetry.config_snapshot
                    else None,
                    telemetry.case_id,
                    telemetry.created_at.isoformat(),
                ),
            )
            self._conn.commit()

    def get_model_telemetry_report(self) -> dict[str, Any]:
        """Aggregate model performance, fallback counts, percentiles, and costs from model_telemetry table."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT
                    provider,
                    model,
                    COUNT(*) as call_count,
                    SUM(CASE WHEN success = 1 AND used_fallback = 0 THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN used_fallback = 1 THEN 1 ELSE 0 END) as fallback_count,
                    AVG(latency_ms) as avg_latency_ms,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens,
                    SUM(cost_usd) as total_cost_usd,
                    MAX(created_at) as last_call_at
                FROM model_telemetry
                GROUP BY provider, model
                ORDER BY call_count DESC;
            """)
            rows = cur.fetchall()

            # Latency percentiles per model
            models_breakdown: list[dict[str, Any]] = []
            total_calls = 0
            total_cost_usd = 0.0
            total_input_tokens = 0
            total_output_tokens = 0

            for r in rows:
                cur.execute(
                    "SELECT latency_ms FROM model_telemetry WHERE provider = ? AND model = ? ORDER BY latency_ms ASC;",
                    (r["provider"], r["model"]),
                )
                latencies = [lat[0] for lat in cur.fetchall()]
                p50 = latencies[len(latencies) // 2] if latencies else 0.0
                p95_idx = int(len(latencies) * 0.95)
                p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0

                call_cnt = r["call_count"]
                cost = float(r["total_cost_usd"] or 0.0)
                in_tok = int(r["total_input_tokens"] or 0)
                out_tok = int(r["total_output_tokens"] or 0)

                total_calls += call_cnt
                total_cost_usd += cost
                total_input_tokens += in_tok
                total_output_tokens += out_tok

                models_breakdown.append(
                    {
                        "provider": r["provider"],
                        "model": r["model"],
                        "call_count": call_cnt,
                        "success_count": r["success_count"],
                        "fallback_count": r["fallback_count"],
                        "avg_latency_ms": round(float(r["avg_latency_ms"] or 0.0), 1),
                        "p50_latency_ms": round(float(p50), 1),
                        "p95_latency_ms": round(float(p95), 1),
                        "total_input_tokens": in_tok,
                        "total_output_tokens": out_tok,
                        "total_cost_usd": round(cost, 6),
                        "last_call_at": r["last_call_at"],
                    }
                )

            return {
                "total_calls": total_calls,
                "total_cost_usd": round(total_cost_usd, 6),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "models": models_breakdown,
            }

    def get_experiments_report(self) -> list[dict[str, Any]]:
        """Compute A/B model experiment comparison stats across experiment tags."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("""
                SELECT
                    c.experiment_tag,
                    t.model,
                    t.provider,
                    COUNT(DISTINCT c.case_id) as cohort_size,
                    SUM(CASE WHEN c.recovered_amount_paise > 0 THEN 1 ELSE 0 END) as recovered_count,
                    SUM(CASE WHEN c.state IN ('FAILED', 'DEAD') THEN 1 ELSE 0 END) as failed_count,
                    AVG(t.latency_ms) as avg_latency_ms,
                    SUM(t.cost_usd) as total_cost_usd
                FROM cases c
                LEFT JOIN model_telemetry t ON c.case_id = t.case_id
                WHERE c.experiment_tag IS NOT NULL
                GROUP BY c.experiment_tag, t.model;
            """)
            rows = cur.fetchall()
            experiments: list[dict[str, Any]] = []
            for r in rows:
                size = r["cohort_size"] or 0
                rec = r["recovered_count"] or 0
                rate = round((rec / size), 4) if size > 0 else 0.0
                experiments.append(
                    {
                        "experiment_tag": r["experiment_tag"],
                        "model": r["model"] or "deterministic-rules-v1",
                        "provider": r["provider"] or "deterministic",
                        "cohort_size": size,
                        "recovered_count": rec,
                        "recovery_rate": rate,
                        "failed_count": r["failed_count"] or 0,
                        "avg_latency_ms": round(float(r["avg_latency_ms"] or 0.0), 1),
                        "total_cost_usd": round(float(r["total_cost_usd"] or 0.0), 6),
                    }
                )
            return experiments

    def get_strategy_experiments_report(self) -> list[dict[str, Any]]:
        """Compute recovery strategy experiments report measuring incremental rupees against holdout arm."""
        with self._lock:
            cur = self._conn.cursor()
            # 1. Compute holdout baseline recovery rate
            cur.execute("""
                SELECT
                    COUNT(*) as holdout_total,
                    SUM(CASE WHEN state = 'RECOVERED' THEN 1 ELSE 0 END) as holdout_rec,
                    SUM(amount_paise) as holdout_at_risk,
                    SUM(recovered_amount_paise) as holdout_rec_amount
                FROM cases
                WHERE experiment_arm = 'HOLDOUT_CONTROL';
            """)
            h_row = cur.fetchone()
            h_total = h_row["holdout_total"] if h_row else 0
            h_rec = h_row["holdout_rec"] if (h_row and h_row["holdout_rec"]) else 0
            holdout_rate = (h_rec / h_total) if h_total > 0 else 0.15

            # 2. Strategy cohort metrics
            cur.execute("""
                SELECT
                    COALESCE(strategy_tag, 'DEFAULT_AUTONOMOUS') as strategy_tag,
                    COUNT(*) as cohort_size,
                    SUM(CASE WHEN state = 'RECOVERED' THEN 1 ELSE 0 END) as recovered_count,
                    SUM(amount_paise) as total_at_risk_paise,
                    SUM(recovered_amount_paise) as gross_recovered_paise,
                    SUM(net_recovered_value_paise) as net_recovered_paise,
                    SUM(total_cost_paise) as total_cost_paise
                FROM cases
                WHERE experiment_arm = 'TREATMENT'
                GROUP BY COALESCE(strategy_tag, 'DEFAULT_AUTONOMOUS');
            """)
            rows = cur.fetchall()
            strategies: list[dict[str, Any]] = []
            for r in rows:
                size = r["cohort_size"] or 0
                rec_cnt = r["recovered_count"] or 0
                at_risk = r["total_at_risk_paise"] or 0
                gross = r["gross_recovered_paise"] or 0
                net = r["net_recovered_paise"] or 0
                cost = r["total_cost_paise"] or 0
                rate = round(rec_cnt / size, 4) if size > 0 else 0.0

                baseline_expected = int(at_risk * holdout_rate)
                incremental = max(0, net - baseline_expected)
                ros = (
                    round(gross / cost, 1)
                    if cost > 0
                    else (100.0 if gross > 0 else 0.0)
                )

                min_conclusive_size = 10
                strategies.append(
                    {
                        "strategy_tag": r["strategy_tag"],
                        "cohort_size": size,
                        "recovered_count": rec_cnt,
                        "recovery_rate": rate,
                        "total_at_risk_paise": at_risk,
                        "gross_recovered_paise": gross,
                        "net_recovered_paise": net,
                        "incremental_recovered_paise": incremental,
                        "total_cost_paise": cost,
                        "return_on_spend": ros,
                        "is_conclusive": size >= min_conclusive_size,
                    }
                )
            return strategies

    def get_pipeline_overview(self) -> dict[str, Any]:
        """Fetch live queue counts and processing rates."""
        now = datetime.now(UTC)
        one_min_ago = (now - timedelta(minutes=1)).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status;")
            status_counts: dict[str, int] = {
                "QUEUED": 0,
                "PROCESSING": 0,
                "DONE": 0,
                "FAILED": 0,
                "DEAD": 0,
            }
            for row in cur.fetchall():
                st = row["status"].upper()
                if st in status_counts:
                    status_counts[st] = int(row["count"])
                elif st == "PENDING":
                    status_counts["QUEUED"] += int(row["count"])

            cur.execute("SELECT COUNT(*) as count FROM cases;")
            total_received = int(cur.fetchone()["count"])

            cur.execute(
                "SELECT COUNT(*) as count FROM cases WHERE created_at >= ?;",
                (one_min_ago,),
            )
            received_last_min = int(cur.fetchone()["count"])

            cur.execute("SELECT COUNT(*) as count FROM jobs WHERE status = 'DONE';")
            total_processed = int(cur.fetchone()["count"])

            cur.execute(
                "SELECT COUNT(*) as count FROM jobs WHERE status = 'DONE' AND updated_at >= ?;",
                (one_min_ago,),
            )
            processed_last_min = int(cur.fetchone()["count"])

            cur.execute(
                "SELECT created_at FROM jobs WHERE status IN ('QUEUED', 'PENDING') ORDER BY created_at ASC LIMIT 1;"
            )
            oldest_row = cur.fetchone()
            oldest_age_sec = 0
            if oldest_row and oldest_row["created_at"]:
                try:
                    oldest_time = datetime.fromisoformat(oldest_row["created_at"])
                    oldest_age_sec = max(0, int((now - oldest_time).total_seconds()))
                except (ValueError, TypeError):
                    pass

            cur.execute("SELECT MAX(created_at) as last_event FROM cases;")
            last_event_row = cur.fetchone()
            last_event = last_event_row["last_event"] if last_event_row else None

            return {
                "counts": status_counts,
                "events_received_total": total_received,
                "events_received_last_minute": received_last_min,
                "events_processed_total": total_processed,
                "events_processed_last_minute": processed_last_min,
                "current_processing_rate_per_min": processed_last_min,
                "backlog_depth": status_counts["QUEUED"] + status_counts["PROCESSING"],
                "oldest_queued_age_seconds": oldest_age_sec,
                "last_event_timestamp": last_event,
            }

    def get_pipeline_timeseries(
        self, bucket_minutes: int = 60, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Fetch timeseries of ingested vs processed events."""
        now = datetime.now(UTC)
        since_time = (now - timedelta(hours=hours)).isoformat()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT created_at FROM cases WHERE created_at >= ? ORDER BY created_at ASC;",
                (since_time,),
            )
            case_times = [
                datetime.fromisoformat(r["created_at"]) for r in cur.fetchall()
            ]

            cur.execute(
                "SELECT updated_at, status FROM jobs WHERE updated_at >= ? ORDER BY updated_at ASC;",
                (since_time,),
            )
            job_rows = [
                (datetime.fromisoformat(r["updated_at"]), r["status"])
                for r in cur.fetchall()
            ]

        num_buckets = max(1, (hours * 60) // max(1, bucket_minutes))
        buckets: list[dict[str, Any]] = []
        bucket_delta = timedelta(minutes=bucket_minutes)
        start_t = now - (bucket_delta * num_buckets)

        for i in range(num_buckets):
            b_start = start_t + (bucket_delta * i)
            b_end = b_start + bucket_delta
            ingested = sum(1 for t in case_times if b_start <= t < b_end)
            done = sum(1 for t, st in job_rows if b_start <= t < b_end and st == "DONE")
            failed = sum(
                1
                for t, st in job_rows
                if b_start <= t < b_end and st in ("FAILED", "DEAD")
            )
            buckets.append(
                {
                    "timestamp": b_end.isoformat(),
                    "ingested": ingested,
                    "processed": done,
                    "failed": failed,
                }
            )
        return buckets

    def get_pipeline_heatmap(self) -> list[dict[str, Any]]:
        """Fetch 7x24 event distribution matrix."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT created_at FROM cases;")
            times = [datetime.fromisoformat(r["created_at"]) for r in cur.fetchall()]

        matrix: dict[tuple[int, int], int] = {
            (d, h): 0 for d in range(7) for h in range(24)
        }
        for t in times:
            d = t.weekday()
            h = t.hour
            matrix[(d, h)] = matrix.get((d, h), 0) + 1

        return [
            {"day": d, "hour": h, "count": matrix[(d, h)]}
            for d in range(7)
            for h in range(24)
        ]

    def fetch_queued_jobs(
        self, limit: int = 50, statuses: list[str] | None = None
    ) -> list[ScheduledJob]:
        """Fetch jobs with optional status filter."""
        target_statuses = statuses or [
            "QUEUED",
            "PENDING",
            "PROCESSING",
            "FAILED",
            "DEAD",
        ]
        placeholders = ",".join("?" for _ in target_statuses)
        with self._lock:
            cur = self._conn.cursor()
            query = f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT ?;"  # noqa: S608
            cur.execute(query, (*target_statuses, limit))
            rows = cur.fetchall()
            jobs: list[ScheduledJob] = []
            for r in rows:
                jobs.append(
                    ScheduledJob(
                        job_id=r["job_id"],
                        case_id=r["case_id"],
                        job_type=r["job_type"],
                        due_at=datetime.fromisoformat(r["due_at"]),
                        status=r["status"],
                        idempotency_key=r["idempotency_key"],
                        attempts=r["attempts"],
                        payload=json.loads(r["payload"]),
                        created_at=datetime.fromisoformat(r["created_at"]),
                        updated_at=datetime.fromisoformat(r["updated_at"]),
                    )
                )
            return jobs

    def clear(self) -> None:
        """Purge all database tables (used for test setup)."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM idempotency_keys;")
            cur.execute("DELETE FROM audit;")
            cur.execute("DELETE FROM jobs;")
            cur.execute("DELETE FROM cases;")
            cur.execute("DELETE FROM model_telemetry;")
            self._conn.commit()
