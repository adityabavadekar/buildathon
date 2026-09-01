"""PostgreSQL-backed ACID relational case storage engine with full query indexing, filtering, and model telemetry."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.audit.models import AuditEntry, ModelTelemetryEntry, RecoveryCase, ScheduledJob
from app.core.db import get_db_connection
from app.core.enums import AuditActor, ExperimentArm, JobStatus, RecoveryState
from app.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = get_logger(__name__)


class RelationalCaseStore:
    """Thread-safe ACID PostgreSQL engine backing case records, audit trails, and jobs."""

    def __init__(self, db_path: Any = None) -> None:
        self._lock = threading.RLock()

    def _serialize_case(self, case: RecoveryCase) -> dict[str, Any]:
        return case.model_dump(mode="json")

    def _deserialize_case(self, data_json: Any) -> RecoveryCase:
        raw = data_json if isinstance(data_json, dict) else json.loads(data_json)
        return RecoveryCase.model_validate(raw)

    def save_case(self, case: RecoveryCase, idempotency_key: str | None = None) -> None:
        """Persist or update a recovery case and flush to PostgreSQL."""
        case_dict = self._serialize_case(case)
        data_json = json.dumps(case_dict)
        now = datetime.now(UTC)

        occurred_at = case.failure_event.occurred_at

        customer_id = (
            getattr(case, "customer_id", None) or case.failure_event.customer_id
        )
        invoice_id = getattr(case, "invoice_id", None) or getattr(
            case.failure_event, "invoice_id", None
        )
        subscription_id = getattr(case, "subscription_id", None) or getattr(
            case.failure_event, "subscription_id", None
        )
        campaign_id = getattr(case, "campaign_id", None) or getattr(
            case.failure_event, "campaign_id", None
        )
        user_ref = getattr(case, "user_ref", None) or getattr(
            case.failure_event, "user_ref", None
        )
        reference_id = getattr(case, "reference_id", None) or getattr(
            case.failure_event, "reference_id", None
        )
        contact_email = getattr(case, "contact_email", None) or getattr(
            case.failure_event, "contact_email", None
        )
        contact_phone = getattr(case, "contact_phone", None) or getattr(
            case.failure_event, "contact_phone", None
        )
        experiment_tag = getattr(case, "experiment_tag", None) or getattr(
            case.failure_event, "experiment_tag", None
        )

        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cases (
                        case_id, payment_id, merchant_id, customer_id, payment_rail,
                        error_code, error_source, state, experiment_arm, amount_paise,
                        currency, touches_count, retry_count, outreach_count,
                        discount_paise_granted, recovered_amount_paise, total_cost_paise,
                        net_recovered_value_paise, is_opted_out, occurred_at, invoice_id,
                        subscription_id, campaign_id, user_ref, reference_id,
                        contact_email, contact_phone, experiment_tag, virtual_account_id,
                        bank_transfer_id, collected_amount_paise, collection_mode,
                        collected_at, payment_link_id, payment_link_url,
                        payment_link_expires_at, strategy_tag, dunning_message_en,
                        dunning_message_hi, due_at, next_action, version, data_json,
                        created_at, updated_at
                    ) VALUES (
                        :case_id, :payment_id, :merchant_id, :customer_id, :payment_rail,
                        :error_code, :error_source, :state, :experiment_arm, :amount_paise,
                        :currency, :touches_count, :retry_count, :outreach_count,
                        :discount_paise_granted, :recovered_amount_paise, :total_cost_paise,
                        :net_recovered_value_paise, :is_opted_out, :occurred_at, :invoice_id,
                        :subscription_id, :campaign_id, :user_ref, :reference_id,
                        :contact_email, :contact_phone, :experiment_tag, :virtual_account_id,
                        :bank_transfer_id, :collected_amount_paise, :collection_mode,
                        :collected_at, :payment_link_id, :payment_link_url,
                        :payment_link_expires_at, :strategy_tag, :dunning_message_en,
                        :dunning_message_hi, :due_at, :next_action, :version, CAST(:data_json AS jsonb),
                        :created_at, :updated_at
                    )
                    ON CONFLICT (case_id) DO UPDATE SET
                        payment_id = EXCLUDED.payment_id,
                        merchant_id = EXCLUDED.merchant_id,
                        customer_id = EXCLUDED.customer_id,
                        payment_rail = EXCLUDED.payment_rail,
                        error_code = EXCLUDED.error_code,
                        error_source = EXCLUDED.error_source,
                        state = EXCLUDED.state,
                        experiment_arm = EXCLUDED.experiment_arm,
                        amount_paise = EXCLUDED.amount_paise,
                        currency = EXCLUDED.currency,
                        touches_count = EXCLUDED.touches_count,
                        retry_count = EXCLUDED.retry_count,
                        outreach_count = EXCLUDED.outreach_count,
                        discount_paise_granted = EXCLUDED.discount_paise_granted,
                        recovered_amount_paise = EXCLUDED.recovered_amount_paise,
                        total_cost_paise = EXCLUDED.total_cost_paise,
                        net_recovered_value_paise = EXCLUDED.net_recovered_value_paise,
                        is_opted_out = EXCLUDED.is_opted_out,
                        occurred_at = EXCLUDED.occurred_at,
                        invoice_id = EXCLUDED.invoice_id,
                        subscription_id = EXCLUDED.subscription_id,
                        campaign_id = EXCLUDED.campaign_id,
                        user_ref = EXCLUDED.user_ref,
                        reference_id = EXCLUDED.reference_id,
                        contact_email = EXCLUDED.contact_email,
                        contact_phone = EXCLUDED.contact_phone,
                        experiment_tag = EXCLUDED.experiment_tag,
                        virtual_account_id = EXCLUDED.virtual_account_id,
                        bank_transfer_id = EXCLUDED.bank_transfer_id,
                        collected_amount_paise = EXCLUDED.collected_amount_paise,
                        collection_mode = EXCLUDED.collection_mode,
                        collected_at = EXCLUDED.collected_at,
                        payment_link_id = EXCLUDED.payment_link_id,
                        payment_link_url = EXCLUDED.payment_link_url,
                        payment_link_expires_at = EXCLUDED.payment_link_expires_at,
                        strategy_tag = EXCLUDED.strategy_tag,
                        dunning_message_en = EXCLUDED.dunning_message_en,
                        dunning_message_hi = EXCLUDED.dunning_message_hi,
                        due_at = EXCLUDED.due_at,
                        next_action = EXCLUDED.next_action,
                        version = cases.version + 1,
                        data_json = EXCLUDED.data_json,
                        updated_at = EXCLUDED.updated_at;
                    """
                ),
                {
                    "case_id": case.case_id,
                    "payment_id": case.failure_event.payment_id,
                    "merchant_id": case.merchant_id,
                    "customer_id": customer_id,
                    "payment_rail": case.failure_event.payment_rail.value
                    if case.failure_event.payment_rail
                    else None,
                    "error_code": case.failure_event.error_code,
                    "error_source": case.failure_event.error_source,
                    "state": case.state.value,
                    "experiment_arm": case.experiment_arm.value,
                    "amount_paise": case.amount_paise,
                    "currency": case.currency,
                    "touches_count": case.touches_count,
                    "retry_count": case.retry_count,
                    "outreach_count": case.outreach_count,
                    "discount_paise_granted": case.discount_paise_granted,
                    "recovered_amount_paise": case.recovered_amount_paise,
                    "total_cost_paise": case.total_cost_paise,
                    "net_recovered_value_paise": case.net_recovered_value_paise,
                    "is_opted_out": case.is_opted_out,
                    "occurred_at": occurred_at,
                    "invoice_id": invoice_id,
                    "subscription_id": subscription_id,
                    "campaign_id": campaign_id,
                    "user_ref": user_ref,
                    "reference_id": reference_id,
                    "contact_email": contact_email,
                    "contact_phone": contact_phone,
                    "experiment_tag": experiment_tag,
                    "virtual_account_id": getattr(case, "virtual_account_id", None),
                    "bank_transfer_id": getattr(case, "bank_transfer_id", None),
                    "collected_amount_paise": getattr(
                        case, "collected_amount_paise", None
                    ),
                    "collection_mode": getattr(case, "collection_mode", None),
                    "collected_at": getattr(case, "collected_at", None),
                    "payment_link_id": getattr(case, "payment_link_id", None),
                    "payment_link_url": getattr(case, "payment_link_url", None),
                    "payment_link_expires_at": getattr(
                        case, "payment_link_expires_at", None
                    ),
                    "strategy_tag": getattr(case, "strategy_tag", None),
                    "dunning_message_en": getattr(case, "dunning_message_en", None),
                    "dunning_message_hi": getattr(case, "dunning_message_hi", None),
                    "due_at": getattr(case, "due_at", None),
                    "next_action": getattr(case, "next_action", None),
                    "version": getattr(case, "version", 1),
                    "data_json": data_json,
                    "created_at": now,
                    "updated_at": now,
                },
            )

            if idempotency_key:
                conn.execute(
                    text(
                        """
                        INSERT INTO idempotency_keys (idempotency_key, case_id, created_at)
                        VALUES (:key, :case_id, :created_at)
                        ON CONFLICT (idempotency_key) DO NOTHING;
                        """
                    ),
                    {
                        "key": idempotency_key,
                        "case_id": case.case_id,
                        "created_at": now,
                    },
                )

            # Persist uncommitted audit entries
            audit_list = getattr(case, "audit_trail", None) or getattr(
                case, "audit_log", []
            )
            for entry in audit_list:
                conn.execute(
                    text(
                        """
                        INSERT INTO audit (
                            entry_id, case_id, event_name, actor, from_state, to_state,
                            reason, notes, decision_inputs, decision_outputs, model_metadata,
                            cost_incurred_paise, timestamp
                        ) VALUES (
                            :entry_id, :case_id, :event_name, :actor, :from_state, :to_state,
                            :reason, :notes, CAST(:decision_inputs AS jsonb), CAST(:decision_outputs AS jsonb),
                            CAST(:model_metadata AS jsonb), :cost_incurred_paise, :timestamp
                        ) ON CONFLICT (entry_id) DO NOTHING;
                        """
                    ),
                    {
                        "entry_id": entry.entry_id,
                        "case_id": entry.case_id,
                        "event_name": entry.event_name,
                        "actor": entry.actor.value,
                        "from_state": entry.from_state.value
                        if entry.from_state
                        else None,
                        "to_state": entry.to_state.value if entry.to_state else None,
                        "reason": getattr(entry, "reason", None) or entry.notes,
                        "notes": entry.notes,
                        "decision_inputs": json.dumps(entry.decision_inputs),
                        "decision_outputs": json.dumps(entry.decision_outputs),
                        "model_metadata": json.dumps(entry.model_metadata)
                        if entry.model_metadata
                        else None,
                        "cost_incurred_paise": entry.cost_incurred_paise,
                        "timestamp": entry.timestamp,
                    },
                )

    def get_case(self, case_id: str) -> RecoveryCase | None:
        """Retrieve a case by unique case ID from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            row = conn.execute(
                text("SELECT data_json FROM cases WHERE case_id = :case_id"),
                {"case_id": case_id},
            ).fetchone()
            if not row or not row[0]:
                return None
            case = self._deserialize_case(row[0])
            case.audit_trail = self.get_audit_trail_for_case(case.case_id)
            return case

    def get_case_by_payment_id(self, payment_id: str) -> RecoveryCase | None:
        """Retrieve a case by payment ID."""
        with self._lock, get_db_connection() as conn:
            row = conn.execute(
                text("SELECT data_json FROM cases WHERE payment_id = :payment_id"),
                {"payment_id": payment_id},
            ).fetchone()
            if not row or not row[0]:
                return None
            case = self._deserialize_case(row[0])
            case.audit_trail = self.get_audit_trail_for_case(case.case_id)
            return case

    def get_case_by_idempotency_key(self, idempotency_key: str) -> RecoveryCase | None:
        """Retrieve a case by idempotency key."""
        with self._lock, get_db_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT c.data_json
                    FROM cases c
                    JOIN idempotency_keys i ON c.case_id = i.case_id
                    WHERE i.idempotency_key = :key
                    LIMIT 1;
                    """
                ),
                {"key": idempotency_key},
            ).fetchone()
            if not row or not row[0]:
                return None
            case = self._deserialize_case(row[0])
            case.audit_trail = self.get_audit_trail_for_case(case.case_id)
            return case

    def get_cases_by_ids(self, case_ids: Sequence[str]) -> list[RecoveryCase]:
        """Retrieve multiple cases by IDs."""
        if not case_ids:
            return []
        with self._lock, get_db_connection() as conn:
            placeholders = ", ".join(f":cid_{i}" for i in range(len(case_ids)))
            params = {f"cid_{i}": cid for i, cid in enumerate(case_ids)}
            rows = conn.execute(
                text(f"SELECT data_json FROM cases WHERE case_id IN ({placeholders})"),  # noqa: S608
                params,
            ).fetchall()
            cases: list[RecoveryCase] = []
            for row in rows:
                if row[0]:
                    c = self._deserialize_case(row[0])
                    c.audit_trail = self.get_audit_trail_for_case(c.case_id)
                    cases.append(c)
            return cases

    def _build_case_filter_query(  # noqa: PLR0912, PLR0915
        self,
        *,
        merchant_id: str | None = None,
        states: Sequence[str] | None = None,
        experiment_arms: Sequence[str] | None = None,
        payment_rails: Sequence[str] | None = None,
        error_codes: Sequence[str] | None = None,
        error_sources: Sequence[str] | None = None,
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
    ) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = ["1=1"]
        params: dict[str, Any] = {}

        if merchant_id:
            clauses.append("merchant_id = :merchant_id")
            params["merchant_id"] = merchant_id
        if states:
            placeholders = ", ".join(f":state_{i}" for i in range(len(states)))
            clauses.append(f"state IN ({placeholders})")
            for i, s in enumerate(states):
                params[f"state_{i}"] = s
        if experiment_arms:
            placeholders = ", ".join(f":arm_{i}" for i in range(len(experiment_arms)))
            clauses.append(f"experiment_arm IN ({placeholders})")
            for i, a in enumerate(experiment_arms):
                params[f"arm_{i}"] = a
        if payment_rails:
            placeholders = ", ".join(f":rail_{i}" for i in range(len(payment_rails)))
            clauses.append(f"payment_rail IN ({placeholders})")
            for i, r in enumerate(payment_rails):
                params[f"rail_{i}"] = r
        if error_codes:
            placeholders = ", ".join(f":err_{i}" for i in range(len(error_codes)))
            clauses.append(f"error_code IN ({placeholders})")
            for i, ec in enumerate(error_codes):
                params[f"err_{i}"] = ec
        if error_sources:
            placeholders = ", ".join(f":src_{i}" for i in range(len(error_sources)))
            clauses.append(f"error_source IN ({placeholders})")
            for i, es in enumerate(error_sources):
                params[f"src_{i}"] = es
        if amount_min_paise is not None:
            clauses.append("amount_paise >= :amount_min")
            params["amount_min"] = amount_min_paise
        if amount_max_paise is not None:
            clauses.append("amount_paise <= :amount_max")
            params["amount_max"] = amount_max_paise
        if created_after is not None:
            clauses.append("created_at >= :created_after")
            params["created_after"] = created_after
        if created_before is not None:
            clauses.append("created_at <= :created_before")
            params["created_before"] = created_before
        if occurred_after is not None:
            clauses.append("occurred_at >= :occurred_after")
            params["occurred_after"] = occurred_after
        if occurred_before is not None:
            clauses.append("occurred_at <= :occurred_before")
            params["occurred_before"] = occurred_before
        if touches_min is not None:
            clauses.append("touches_count >= :touches_min")
            params["touches_min"] = touches_min
        if touches_max is not None:
            clauses.append("touches_count <= :touches_max")
            params["touches_max"] = touches_max
        if recovered is True:
            clauses.append("state = 'RECOVERED'")
        elif recovered is False:
            clauses.append("state != 'RECOVERED'")
        if opted_out is not None:
            clauses.append("is_opted_out = :opted_out")
            params["opted_out"] = opted_out
        if has_escalation is not None:
            if has_escalation:
                clauses.append("state = 'ESCALATED_HUMAN'")
            else:
                clauses.append("state != 'ESCALATED_HUMAN'")
        if customer_id:
            clauses.append("customer_id = :customer_id")
            params["customer_id"] = customer_id
        if payment_id:
            clauses.append("payment_id = :payment_id")
            params["payment_id"] = payment_id
        if invoice_id:
            clauses.append("invoice_id = :invoice_id")
            params["invoice_id"] = invoice_id
        if subscription_id:
            clauses.append("subscription_id = :subscription_id")
            params["subscription_id"] = subscription_id
        if campaign_id:
            clauses.append("campaign_id = :campaign_id")
            params["campaign_id"] = campaign_id
        if user_ref:
            clauses.append("user_ref = :user_ref")
            params["user_ref"] = user_ref
        if reference_id:
            clauses.append("reference_id = :reference_id")
            params["reference_id"] = reference_id
        if q:
            clauses.append(
                """(
                    payment_id ILIKE :q_like OR
                    customer_id ILIKE :q_like OR
                    invoice_id ILIKE :q_like OR
                    subscription_id ILIKE :q_like OR
                    campaign_id ILIKE :q_like OR
                    user_ref ILIKE :q_like OR
                    reference_id ILIKE :q_like OR
                    contact_email ILIKE :q_like OR
                    contact_phone ILIKE :q_like OR
                    case_id ILIKE :q_like OR
                    error_code ILIKE :q_like OR
                    error_source ILIKE :q_like OR
                    CAST(data_json AS text) ILIKE :q_like
                )"""
            )
            params["q_like"] = f"%{q}%"
        if model_used:
            clauses.append(
                """case_id IN (
                    SELECT DISTINCT case_id FROM model_telemetry WHERE model = :model_used
                )"""
            )
            params["model_used"] = model_used

        return " AND ".join(clauses), params

    def list_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: Sequence[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: Sequence[str] | None = None,
        payment_rails: Sequence[str] | None = None,
        error_codes: Sequence[str] | None = None,
        error_sources: Sequence[str] | None = None,
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
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        sort_order: str = "desc",
    ) -> list[RecoveryCase]:
        """List cases filtered across multiple dimensions in PostgreSQL."""
        state_list = [state.value] if state else list(states or [])
        arm_list = (
            [experiment_arm.value] if experiment_arm else list(experiment_arms or [])
        )

        where_clause, params = self._build_case_filter_query(
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

        valid_sort_columns = {
            "created_at",
            "occurred_at",
            "amount_paise",
            "touches_count",
            "recovered_amount_paise",
            "net_recovered_value_paise",
            "state",
        }
        col = sort_by if sort_by in valid_sort_columns else "created_at"
        direction = sort_dir or sort_order
        order = "DESC" if direction.lower() == "desc" else "ASC"

        query = f"""
            SELECT data_json
            FROM cases
            WHERE {where_clause}
            ORDER BY {col} {order}
            LIMIT :limit OFFSET :offset;
        """  # noqa: S608

        params["limit"] = limit
        params["offset"] = offset

        with self._lock, get_db_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            cases: list[RecoveryCase] = []
            for row in rows:
                if row[0]:
                    case = self._deserialize_case(row[0])
                    cases.append(case)
            return cases

    def count_cases(
        self,
        *,
        merchant_id: str | None = None,
        state: RecoveryState | None = None,
        states: Sequence[str] | None = None,
        experiment_arm: ExperimentArm | None = None,
        experiment_arms: Sequence[str] | None = None,
        payment_rails: Sequence[str] | None = None,
        error_codes: Sequence[str] | None = None,
        error_sources: Sequence[str] | None = None,
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
        """Count cases matching arbitrary search criteria in PostgreSQL."""
        state_list = [state.value] if state else list(states or [])
        arm_list = (
            [experiment_arm.value] if experiment_arm else list(experiment_arms or [])
        )

        where_clause, params = self._build_case_filter_query(
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

        query = f"SELECT COUNT(*) FROM cases WHERE {where_clause};"  # noqa: S608
        with self._lock, get_db_connection() as conn:
            cnt = conn.execute(text(query), params).scalar()
            return int(cnt or 0)

    def get_audit_trail_for_case(self, case_id: str) -> list[AuditEntry]:
        """Fetch immutable audit entries for a case from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM audit WHERE case_id = :case_id ORDER BY timestamp ASC"
                    ),
                    {"case_id": case_id},
                )
                .mappings()
                .fetchall()
            )

            entries: list[AuditEntry] = []
            for r in rows:
                raw_in = r["decision_inputs"]
                d_in = (
                    raw_in
                    if isinstance(raw_in, dict)
                    else (json.loads(raw_in) if raw_in else {})
                )
                raw_out = r["decision_outputs"]
                d_out = (
                    raw_out
                    if isinstance(raw_out, dict)
                    else (json.loads(raw_out) if raw_out else {})
                )
                raw_meta = r["model_metadata"]
                d_meta = (
                    raw_meta
                    if isinstance(raw_meta, dict)
                    else (json.loads(raw_meta) if raw_meta else None)
                )

                ts = r["timestamp"]
                ts_dt = (
                    ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
                )

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
                        decision_inputs=d_in,
                        decision_outputs=d_out,
                        model_metadata=d_meta,
                        cost_incurred_paise=r["cost_incurred_paise"],
                        timestamp=ts_dt,
                    )
                )
            return entries

    def schedule_job(self, job: ScheduledJob) -> None:
        """Schedule a background execution job in PostgreSQL with idempotency deduplication."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO jobs (
                        job_id, case_id, job_type, due_at, status,
                        idempotency_key, attempts, payload, created_at, updated_at
                    ) VALUES (
                        :job_id, :case_id, :job_type, :due_at, :status,
                        :idempotency_key, :attempts, CAST(:payload AS jsonb), :created_at, :updated_at
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                        due_at = EXCLUDED.due_at,
                        status = EXCLUDED.status,
                        attempts = EXCLUDED.attempts,
                        updated_at = EXCLUDED.updated_at;
                    """
                ),
                {
                    "job_id": job.job_id,
                    "case_id": job.case_id,
                    "job_type": job.job_type,
                    "due_at": job.due_at,
                    "status": job.status,
                    "idempotency_key": job.idempotency_key,
                    "attempts": job.attempts,
                    "payload": json.dumps(job.payload),
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                },
            )

    def fetch_due_jobs(self, limit: int = 20) -> list[ScheduledJob]:
        """Fetch pending jobs ready for execution whose due_at has passed in PostgreSQL."""
        now = datetime.now(UTC)
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        """
                    SELECT * FROM jobs
                    WHERE status IN ('QUEUED', 'PENDING') AND due_at <= :now
                    ORDER BY due_at ASC LIMIT :limit;
                    """
                    ),
                    {"now": now, "limit": limit},
                )
                .mappings()
                .fetchall()
            )

            jobs: list[ScheduledJob] = []
            for r in rows:
                raw_payload = r["payload"]
                payload = (
                    raw_payload
                    if isinstance(raw_payload, dict)
                    else json.loads(raw_payload)
                )
                due = r["due_at"]
                due_dt = (
                    due
                    if isinstance(due, datetime)
                    else datetime.fromisoformat(str(due))
                )
                cat = r["created_at"]
                cat_dt = (
                    cat
                    if isinstance(cat, datetime)
                    else datetime.fromisoformat(str(cat))
                )
                uat = r["updated_at"]
                uat_dt = (
                    uat
                    if isinstance(uat, datetime)
                    else datetime.fromisoformat(str(uat))
                )

                jobs.append(
                    ScheduledJob(
                        job_id=r["job_id"],
                        case_id=r["case_id"],
                        job_type=r["job_type"],
                        due_at=due_dt,
                        status=r["status"],
                        idempotency_key=r["idempotency_key"],
                        attempts=r["attempts"],
                        payload=payload,
                        created_at=cat_dt,
                        updated_at=uat_dt,
                    )
                )
            return jobs

    def fetch_queued_jobs(
        self, limit: int = 50, statuses: list[str] | None = None
    ) -> list[ScheduledJob]:
        """Fetch jobs with optional status filter from PostgreSQL."""
        target_statuses = statuses or [
            "QUEUED",
            "PENDING",
            "PROCESSING",
            "FAILED",
            "DEAD",
        ]
        placeholders = ", ".join(f":st_{i}" for i in range(len(target_statuses)))
        params: dict[str, Any] = {f"st_{i}": st for i, st in enumerate(target_statuses)}
        params["limit"] = limit

        query = f"""
            SELECT * FROM jobs
            WHERE status IN ({placeholders})
            ORDER BY updated_at DESC
            LIMIT :limit;
        """  # noqa: S608

        with self._lock, get_db_connection() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()
            jobs: list[ScheduledJob] = []
            for r in rows:
                raw_payload = r["payload"]
                payload = (
                    raw_payload
                    if isinstance(raw_payload, dict)
                    else json.loads(raw_payload)
                )
                due = r["due_at"]
                due_dt = (
                    due
                    if isinstance(due, datetime)
                    else datetime.fromisoformat(str(due))
                )
                cat = r["created_at"]
                cat_dt = (
                    cat
                    if isinstance(cat, datetime)
                    else datetime.fromisoformat(str(cat))
                )
                uat = r["updated_at"]
                uat_dt = (
                    uat
                    if isinstance(uat, datetime)
                    else datetime.fromisoformat(str(uat))
                )

                jobs.append(
                    ScheduledJob(
                        job_id=r["job_id"],
                        case_id=r["case_id"],
                        job_type=r["job_type"],
                        due_at=due_dt,
                        status=r["status"],
                        idempotency_key=r["idempotency_key"],
                        attempts=r["attempts"],
                        payload=payload,
                        created_at=cat_dt,
                        updated_at=uat_dt,
                    )
                )
            return jobs

    def claim_next_due_job(self, now: datetime | None = None) -> ScheduledJob | None:
        """Atomically claim next due job using SELECT ... FOR UPDATE SKIP LOCKED in PostgreSQL."""
        now_val = now or datetime.now(UTC)
        with self._lock, get_db_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                    SELECT job_id, case_id, job_type, due_at, status,
                           idempotency_key, attempts, payload, created_at, updated_at
                    FROM jobs
                    WHERE status IN ('QUEUED', 'PENDING') AND due_at <= :now
                    ORDER BY due_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1;
                    """
                    ),
                    {"now": now_val},
                )
                .mappings()
                .fetchone()
            )

            if not row:
                return None

            job_id = row["job_id"]
            new_attempts = row["attempts"] + 1

            conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = 'PROCESSING', attempts = :attempts, updated_at = :updated_at
                    WHERE job_id = :job_id;
                    """
                ),
                {"attempts": new_attempts, "updated_at": now_val, "job_id": job_id},
            )

            raw_payload = row["payload"]
            payload = (
                raw_payload
                if isinstance(raw_payload, dict)
                else json.loads(raw_payload)
            )
            due = row["due_at"]
            due_dt = (
                due if isinstance(due, datetime) else datetime.fromisoformat(str(due))
            )
            cat = row["created_at"]
            cat_dt = (
                cat if isinstance(cat, datetime) else datetime.fromisoformat(str(cat))
            )

            return ScheduledJob(
                job_id=row["job_id"],
                case_id=row["case_id"],
                job_type=row["job_type"],
                due_at=due_dt,
                status=JobStatus.PROCESSING.value,
                idempotency_key=row["idempotency_key"],
                attempts=new_attempts,
                payload=payload,
                created_at=cat_dt,
                updated_at=now_val,
            )

    def reclaim_stuck_processing_jobs(self, max_processing_seconds: int = 60) -> int:
        """Reclaim orphaned jobs stuck in PROCESSING on worker crash."""
        cutoff = datetime.now(UTC) - timedelta(seconds=max_processing_seconds)
        now = datetime.now(UTC)
        with self._lock, get_db_connection() as conn:
            res = conn.execute(
                text(
                    """
                    UPDATE jobs
                    SET status = 'QUEUED', updated_at = :now
                    WHERE status = 'PROCESSING' AND updated_at <= :cutoff;
                    """
                ),
                {"now": now, "cutoff": cutoff},
            )
            return max(0, res.rowcount)

    def update_job_status(
        self, job_id: str, status: str, attempts: int | None = None
    ) -> None:
        """Update job status and attempts in PostgreSQL."""
        now = datetime.now(UTC)
        with self._lock, get_db_connection() as conn:
            if attempts is not None:
                conn.execute(
                    text(
                        """
                        UPDATE jobs SET status = :status, attempts = :attempts, updated_at = :updated_at
                        WHERE job_id = :job_id;
                        """
                    ),
                    {
                        "status": status,
                        "attempts": attempts,
                        "updated_at": now,
                        "job_id": job_id,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE jobs SET status = :status, updated_at = :updated_at
                        WHERE job_id = :job_id;
                        """
                    ),
                    {"status": status, "updated_at": now, "job_id": job_id},
                )

    def record_model_telemetry(self, telemetry: ModelTelemetryEntry) -> None:
        """Record model invocation telemetry directly to model_telemetry PostgreSQL table."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO model_telemetry (
                        id, model, provider, version, input_tokens, output_tokens,
                        cost_usd, latency_ms, success, used_fallback, fallback_reason,
                        experiment_tag, config_snapshot, case_id, created_at
                    ) VALUES (
                        :id, :model, :provider, :version, :input_tokens, :output_tokens,
                        :cost_usd, :latency_ms, :success, :used_fallback, :fallback_reason,
                        :experiment_tag, CAST(:config_snapshot AS jsonb), :case_id, :created_at
                    );
                    """
                ),
                {
                    "id": telemetry.id,
                    "model": telemetry.model,
                    "provider": telemetry.provider,
                    "version": telemetry.version,
                    "input_tokens": telemetry.input_tokens,
                    "output_tokens": telemetry.output_tokens,
                    "cost_usd": telemetry.cost_usd,
                    "latency_ms": telemetry.latency_ms,
                    "success": telemetry.success,
                    "used_fallback": telemetry.used_fallback,
                    "fallback_reason": telemetry.fallback_reason,
                    "experiment_tag": telemetry.experiment_tag,
                    "config_snapshot": json.dumps(telemetry.config_snapshot)
                    if telemetry.config_snapshot
                    else None,
                    "case_id": telemetry.case_id,
                    "created_at": telemetry.created_at,
                },
            )

    def get_model_telemetry_report(self) -> dict[str, Any]:
        """Aggregate model performance, fallback counts, percentiles, and costs from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        """
                    SELECT
                        provider,
                        model,
                        COUNT(*) as call_count,
                        SUM(CASE WHEN success = true AND used_fallback = false THEN 1 ELSE 0 END) as success_count,
                        SUM(CASE WHEN used_fallback = true THEN 1 ELSE 0 END) as fallback_count,
                        AVG(latency_ms) as avg_latency_ms,
                        SUM(input_tokens) as total_input_tokens,
                        SUM(output_tokens) as total_output_tokens,
                        SUM(cost_usd) as total_cost_usd,
                        MAX(created_at) as last_call_at
                    FROM model_telemetry
                    GROUP BY provider, model
                    ORDER BY call_count DESC;
                    """
                    )
                )
                .mappings()
                .fetchall()
            )

            models_breakdown: list[dict[str, Any]] = []
            total_calls = 0
            total_cost_usd = 0.0
            total_input_tokens = 0
            total_output_tokens = 0

            for r in rows:
                lat_rows = conn.execute(
                    text(
                        "SELECT latency_ms FROM model_telemetry WHERE provider = :prov AND model = :model ORDER BY latency_ms ASC"
                    ),
                    {"prov": r["provider"], "model": r["model"]},
                ).fetchall()
                latencies = [lat[0] for lat in lat_rows]
                p50 = latencies[len(latencies) // 2] if latencies else 0.0
                p95_idx = int(len(latencies) * 0.95)
                p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0

                call_cnt = int(r["call_count"])
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
                        "success_count": int(r["success_count"] or 0),
                        "fallback_count": int(r["fallback_count"] or 0),
                        "avg_latency_ms": round(float(r["avg_latency_ms"] or 0.0), 2),
                        "p50_latency_ms": round(float(p50), 2),
                        "p95_latency_ms": round(float(p95), 2),
                        "total_input_tokens": in_tok,
                        "total_output_tokens": out_tok,
                        "total_cost_usd": round(cost, 6),
                        "last_call_at": r["last_call_at"].isoformat()
                        if hasattr(r["last_call_at"], "isoformat")
                        else str(r["last_call_at"]),
                    }
                )

            return {
                "total_calls": total_calls,
                "total_cost_usd": round(total_cost_usd, 6),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "models": models_breakdown,
            }

    def list_model_telemetry(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        experiment_tag: str | None = None,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[ModelTelemetryEntry]:
        """Fetch individual telemetry traces with optional filters from PostgreSQL."""
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if model:
            clauses.append("model = :model")
            params["model"] = model
        if provider:
            clauses.append("provider = :provider")
            params["provider"] = provider
        if experiment_tag:
            clauses.append("experiment_tag = :experiment_tag")
            params["experiment_tag"] = experiment_tag
        if case_id:
            clauses.append("case_id = :case_id")
            params["case_id"] = case_id

        query = f"""
            SELECT * FROM model_telemetry
            WHERE {" AND ".join(clauses)}
            ORDER BY created_at DESC
            LIMIT :limit;
        """  # noqa: S608

        with self._lock, get_db_connection() as conn:
            rows = conn.execute(text(query), params).mappings().fetchall()
            entries: list[ModelTelemetryEntry] = []
            for r in rows:
                raw_cfg = r["config_snapshot"]
                cfg = (
                    raw_cfg
                    if isinstance(raw_cfg, dict)
                    else (json.loads(raw_cfg) if raw_cfg else None)
                )
                cat = r["created_at"]
                cat_dt = (
                    cat
                    if isinstance(cat, datetime)
                    else datetime.fromisoformat(str(cat))
                )

                entries.append(
                    ModelTelemetryEntry(
                        id=r["id"],
                        model=r["model"],
                        provider=r["provider"],
                        version=r["version"],
                        input_tokens=r["input_tokens"],
                        output_tokens=r["output_tokens"],
                        cost_usd=r["cost_usd"],
                        latency_ms=r["latency_ms"],
                        success=bool(r["success"]),
                        used_fallback=bool(r["used_fallback"]),
                        fallback_reason=r["fallback_reason"],
                        experiment_tag=r["experiment_tag"],
                        config_snapshot=cfg,
                        case_id=r["case_id"],
                        created_at=cat_dt,
                    )
                )
            return entries

    def get_experiments_report(self) -> list[dict[str, Any]]:
        """Compute A/B model experiment comparison stats across experiment tags from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        """
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
                    GROUP BY c.experiment_tag, t.model, t.provider;
                    """
                    )
                )
                .mappings()
                .fetchall()
            )

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
        """Compute recovery strategy experiments report measuring incremental value against holdout arm."""
        with self._lock, get_db_connection() as conn:
            h_row = (
                conn.execute(
                    text(
                        """
                    SELECT
                        COUNT(*) as holdout_total,
                        SUM(CASE WHEN state = 'RECOVERED' THEN 1 ELSE 0 END) as holdout_rec,
                        SUM(amount_paise) as holdout_at_risk,
                        SUM(recovered_amount_paise) as holdout_rec_amount
                    FROM cases
                    WHERE experiment_arm = 'HOLDOUT_CONTROL';
                    """
                    )
                )
                .mappings()
                .fetchone()
            )
            h_total = h_row["holdout_total"] if h_row and h_row["holdout_total"] else 0
            h_rec = h_row["holdout_rec"] if h_row and h_row["holdout_rec"] else 0
            holdout_rate = (h_rec / h_total) if h_total > 0 else 0.15

            rows = (
                conn.execute(
                    text(
                        """
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
                    """
                    )
                )
                .mappings()
                .fetchall()
            )

            strategies: list[dict[str, Any]] = []
            for r in rows:
                size = int(r["cohort_size"] or 0)
                rec_cnt = int(r["recovered_count"] or 0)
                at_risk = int(r["total_at_risk_paise"] or 0)
                gross = int(r["gross_recovered_paise"] or 0)
                net = int(r["net_recovered_paise"] or 0)
                cost = int(r["total_cost_paise"] or 0)
                rate = round(rec_cnt / size, 4) if size > 0 else 0.0

                baseline_expected = int(float(at_risk) * float(holdout_rate))
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
        """Fetch live queue counts and processing rates from PostgreSQL."""
        now = datetime.now(UTC)
        one_min_ago = now - timedelta(minutes=1)
        with self._lock, get_db_connection() as conn:
            status_rows = conn.execute(
                text("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
            ).fetchall()
            status_counts: dict[str, int] = {
                "QUEUED": 0,
                "PROCESSING": 0,
                "DONE": 0,
                "FAILED": 0,
                "DEAD": 0,
            }
            for row in status_rows:
                st = row[0].upper()
                cnt = int(row[1])
                if st in status_counts:
                    status_counts[st] = cnt
                elif st == "PENDING":
                    status_counts["QUEUED"] += cnt

            queues_due_now = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*) FROM jobs
                        WHERE status IN ('QUEUED', 'PENDING') AND due_at <= :now;
                        """
                    ),
                    {"now": now},
                ).scalar()
                or 0
            )
            queues_total = status_counts["QUEUED"]
            status_counts["QUEUED_DUE_NOW"] = queues_due_now
            status_counts["QUEUED_FUTURE"] = queues_total - queues_due_now

            total_received = int(
                conn.execute(text("SELECT COUNT(*) FROM cases")).scalar() or 0
            )
            received_last_min = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM cases WHERE created_at >= :one_min_ago"),
                    {"one_min_ago": one_min_ago},
                ).scalar()
                or 0
            )

            total_processed = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM jobs WHERE status = 'DONE'")
                ).scalar()
                or 0
            )
            processed_last_min = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM jobs WHERE status = 'DONE' AND updated_at >= :one_min_ago"
                    ),
                    {"one_min_ago": one_min_ago},
                ).scalar()
                or 0
            )

            oldest_time_val = conn.execute(
                text(
                    "SELECT created_at FROM jobs WHERE status IN ('QUEUED', 'PENDING') ORDER BY created_at ASC LIMIT 1"
                )
            ).scalar()
            oldest_age_sec = 0
            if oldest_time_val is not None:
                try:
                    oldest_time = (
                        oldest_time_val
                        if isinstance(oldest_time_val, datetime)
                        else datetime.fromisoformat(str(oldest_time_val))
                    )
                    oldest_age_sec = max(0, int((now - oldest_time).total_seconds()))
                except (ValueError, TypeError):
                    pass

            last_event_val = conn.execute(
                text("SELECT MAX(created_at) FROM cases")
            ).scalar()
            last_event = (
                last_event_val.isoformat()
                if isinstance(last_event_val, datetime)
                else (str(last_event_val) if last_event_val is not None else None)
            )

            return {
                "counts": status_counts,
                "backlog_depth": queues_due_now + status_counts["PROCESSING"],
                "events_received_total": total_received,
                "events_received_last_minute": received_last_min,
                "events_processed_total": total_processed,
                "events_processed_last_minute": processed_last_min,
                "oldest_queued_age_seconds": oldest_age_sec,
                "last_event_timestamp": last_event,
            }

    def get_pipeline_timeseries(
        self, bucket_minutes: int = 60, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Fetch timeseries of ingested vs processed events from PostgreSQL."""
        now = datetime.now(UTC)
        since_time = now - timedelta(hours=hours)
        with self._lock, get_db_connection() as conn:
            case_rows = conn.execute(
                text(
                    "SELECT created_at FROM cases WHERE created_at >= :since ORDER BY created_at ASC"
                ),
                {"since": since_time},
            ).fetchall()
            case_times = [
                (
                    r[0]
                    if isinstance(r[0], datetime)
                    else datetime.fromisoformat(str(r[0]))
                )
                for r in case_rows
            ]

            job_rows = conn.execute(
                text(
                    "SELECT updated_at, status FROM jobs WHERE updated_at >= :since ORDER BY updated_at ASC"
                ),
                {"since": since_time},
            ).fetchall()
            job_tuples = [
                (
                    r[0]
                    if isinstance(r[0], datetime)
                    else datetime.fromisoformat(str(r[0])),
                    str(r[1]),
                )
                for r in job_rows
            ]

        num_buckets = max(1, (hours * 60) // max(1, bucket_minutes))
        buckets: list[dict[str, Any]] = []
        bucket_delta = timedelta(minutes=bucket_minutes)
        start_t = now - (bucket_delta * num_buckets)

        for i in range(num_buckets):
            b_start = start_t + (bucket_delta * i)
            b_end = b_start + bucket_delta
            ingested = sum(1 for t in case_times if b_start <= t < b_end)
            done = sum(
                1 for t, st in job_tuples if b_start <= t < b_end and st == "DONE"
            )
            failed = sum(
                1
                for t, st in job_tuples
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
        """Fetch 7x24 event distribution matrix from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = conn.execute(text("SELECT created_at FROM cases")).fetchall()
            times = [
                (
                    r[0]
                    if isinstance(r[0], datetime)
                    else datetime.fromisoformat(str(r[0]))
                )
                for r in rows
            ]

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

    def clear(self) -> None:
        """Purge all database tables in PostgreSQL (used for test teardown)."""
        with self._lock, get_db_connection() as conn:
            conn.execute(text("DELETE FROM idempotency_keys;"))
            conn.execute(text("DELETE FROM audit;"))
            conn.execute(text("DELETE FROM jobs;"))
            conn.execute(text("DELETE FROM cases;"))
            conn.execute(text("DELETE FROM model_telemetry;"))
            conn.execute(text("DELETE FROM ml_models;"))
            conn.execute(text("DELETE FROM ml_predictions;"))
            conn.execute(text("DELETE FROM pattern_alerts;"))
            conn.execute(text("DELETE FROM workflow_events;"))
            conn.execute(text("DELETE FROM workflow_signals;"))
            conn.execute(text("DELETE FROM workflows;"))
            conn.execute(
                text(
                    "DELETE FROM workflow_template_definitions WHERE is_builtin = false;"
                )
            )

    def save_ml_model(self, model: dict[str, Any]) -> None:
        """Save trained ML model artifact dictionary."""
        with self._lock, get_db_connection() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ml_models (
                        model_id, version, artifact_json, feature_schema_json,
                        train_arm, seed, holdout_metrics_json, trained_at
                    ) VALUES (
                        :model_id, :version, CAST(:artifact_json AS jsonb),
                        CAST(:feature_schema_json AS jsonb), :train_arm, :seed,
                        CAST(:holdout_metrics_json AS jsonb), :trained_at
                    ) ON CONFLICT (model_id) DO UPDATE SET
                        artifact_json = EXCLUDED.artifact_json,
                        feature_schema_json = EXCLUDED.feature_schema_json,
                        holdout_metrics_json = EXCLUDED.holdout_metrics_json,
                        trained_at = EXCLUDED.trained_at;
                    """
                ),
                {
                    "model_id": model["model_id"],
                    "version": model["version"],
                    "artifact_json": json.dumps(model["artifact"])
                    if not isinstance(model["artifact"], str)
                    else model["artifact"],
                    "feature_schema_json": json.dumps(model["feature_schema"])
                    if not isinstance(model["feature_schema"], str)
                    else model["feature_schema"],
                    "train_arm": model["train_arm"],
                    "seed": model["seed"],
                    "holdout_metrics_json": json.dumps(model["holdout_metrics"])
                    if not isinstance(model["holdout_metrics"], str)
                    else model["holdout_metrics"],
                    "trained_at": model["trained_at"],
                },
            )

    def get_ml_model(self) -> dict[str, Any] | None:
        """Retrieve latest trained ML model artifact dictionary."""
        with self._lock, get_db_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM ml_models ORDER BY trained_at DESC LIMIT 1")
                )
                .mappings()
                .fetchone()
            )
            if row is None:
                return None
            raw_art = row["artifact_json"]
            art = raw_art if isinstance(raw_art, dict) else json.loads(raw_art)
            raw_schema = row["feature_schema_json"]
            schema = (
                raw_schema if isinstance(raw_schema, dict) else json.loads(raw_schema)
            )
            raw_metrics = row["holdout_metrics_json"]
            metrics = (
                raw_metrics
                if isinstance(raw_metrics, dict)
                else json.loads(raw_metrics)
            )
            cat = row["trained_at"]
            cat_str = cat.isoformat() if hasattr(cat, "isoformat") else str(cat)
            return {
                "model_id": row["model_id"],
                "version": row["version"],
                "artifact": art,
                "feature_schema": schema,
                "train_arm": row["train_arm"],
                "seed": row["seed"],
                "holdout_metrics": metrics,
                "trained_at": cat_str,
            }

    def save_ml_predictions(self, predictions: list[dict[str, Any]]) -> None:
        """Persist ML prediction event records."""
        with self._lock, get_db_connection() as conn:
            for item in predictions:
                conn.execute(
                    text(
                        """
                        INSERT INTO ml_predictions (
                            prediction_id, case_id, model_id, prediction_type,
                            score, inputs_json, created_at
                        ) VALUES (
                            :prediction_id, :case_id, :model_id, :prediction_type,
                            :score, CAST(:inputs_json AS jsonb), :created_at
                        ) ON CONFLICT (prediction_id) DO NOTHING;
                        """
                    ),
                    {
                        "prediction_id": item["prediction_id"],
                        "case_id": item["case_id"],
                        "model_id": item["model_id"],
                        "prediction_type": item["prediction_type"],
                        "score": item["score"],
                        "inputs_json": json.dumps(item["inputs"])
                        if not isinstance(item["inputs"], str)
                        else item["inputs"],
                        "created_at": item["created_at"],
                    },
                )

    def save_pattern_alerts(self, alerts: list[dict[str, Any]]) -> None:
        """Save k-means pattern alert clusters in PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            for alert in alerts:
                conn.execute(
                    text(
                        """
                        INSERT INTO pattern_alerts (
                            alert_id, run_id, seed, feature_scope, dominant_category,
                            dominant_intervention, member_count, mean_amount_paise,
                            example_case_ids_json, created_at
                        ) VALUES (
                            :alert_id, :run_id, :seed, :feature_scope, :dominant_category,
                            :dominant_intervention, :member_count, :mean_amount_paise,
                            CAST(:example_case_ids_json AS jsonb), :created_at
                        ) ON CONFLICT (alert_id) DO UPDATE SET
                            run_id = EXCLUDED.run_id,
                            seed = EXCLUDED.seed,
                            feature_scope = EXCLUDED.feature_scope,
                            dominant_category = EXCLUDED.dominant_category,
                            dominant_intervention = EXCLUDED.dominant_intervention,
                            member_count = EXCLUDED.member_count,
                            mean_amount_paise = EXCLUDED.mean_amount_paise,
                            example_case_ids_json = EXCLUDED.example_case_ids_json;
                        """
                    ),
                    {
                        "alert_id": alert["alert_id"],
                        "run_id": alert["run_id"],
                        "seed": alert["seed"],
                        "feature_scope": alert["feature_scope"],
                        "dominant_category": alert["dominant_category"],
                        "dominant_intervention": alert["dominant_intervention"],
                        "member_count": alert["member_count"],
                        "mean_amount_paise": alert["mean_amount_paise"],
                        "example_case_ids_json": json.dumps(alert["example_case_ids"]),
                        "created_at": alert["created_at"],
                    },
                )

    def list_pattern_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        """List latest pattern alerts from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM pattern_alerts ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .mappings()
                .fetchall()
            )

            alerts: list[dict[str, Any]] = []
            for r in rows:
                raw_ex = r["example_case_ids_json"]
                ex = raw_ex if isinstance(raw_ex, list) else json.loads(raw_ex)
                cat = r["created_at"]
                cat_str = cat.isoformat() if hasattr(cat, "isoformat") else str(cat)
                alerts.append(
                    {
                        "alert_id": r["alert_id"],
                        "run_id": r["run_id"],
                        "seed": r["seed"],
                        "feature_scope": r["feature_scope"],
                        "dominant_category": r["dominant_category"],
                        "dominant_intervention": r["dominant_intervention"],
                        "member_count": r["member_count"],
                        "mean_amount_paise": r["mean_amount_paise"],
                        "example_case_ids": ex,
                        "created_at": cat_str,
                    }
                )
            return alerts

    def list_ml_predictions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List latest ML inference events from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT * FROM ml_predictions ORDER BY created_at DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                .mappings()
                .fetchall()
            )
            return [dict(r) for r in rows]

    def get_analytics_summary(self) -> dict[str, Any]:
        """Aggregate recovery KPI metrics from PostgreSQL."""
        with self._lock, get_db_connection() as conn:
            total_cases = int(
                conn.execute(text("SELECT COUNT(*) FROM cases")).scalar() or 0
            )
            recovered_cases = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM cases WHERE state = 'RECOVERED'")
                ).scalar()
                or 0
            )
            total_value = int(
                conn.execute(text("SELECT SUM(amount_paise) FROM cases")).scalar() or 0
            )
            recovered_value = int(
                conn.execute(
                    text("SELECT SUM(recovered_amount_paise) FROM cases")
                ).scalar()
                or 0
            )
            total_costs = int(
                conn.execute(text("SELECT SUM(total_cost_paise) FROM cases")).scalar()
                or 0
            )
            net_recovered = int(
                conn.execute(
                    text("SELECT SUM(net_recovered_value_paise) FROM cases")
                ).scalar()
                or 0
            )

            return {
                "total_cases": total_cases,
                "recovered_cases": recovered_cases,
                "recovery_rate": round(recovered_cases / total_cases, 4)
                if total_cases > 0
                else 0.0,
                "total_value_paise": total_value,
                "recovered_value_paise": recovered_value,
                "total_cost_paise": total_costs,
                "net_recovered_value_paise": net_recovered,
            }
