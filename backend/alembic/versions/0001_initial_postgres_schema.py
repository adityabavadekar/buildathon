"""0001_initial_postgres_schema

Revision ID: 0001
Revises:
Create Date: 2026-08-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Cases Table
    op.create_table(
        "cases",
        sa.Column("case_id", sa.Text(), primary_key=True),
        sa.Column("payment_id", sa.Text(), nullable=False, unique=True),
        sa.Column("merchant_id", sa.Text(), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=True),
        sa.Column("payment_rail", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_source", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("experiment_arm", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="INR"),
        sa.Column("touches_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outreach_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "discount_paise_granted",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "recovered_amount_paise",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_cost_paise", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "net_recovered_value_paise",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_opted_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invoice_id", sa.Text(), nullable=True),
        sa.Column("subscription_id", sa.Text(), nullable=True),
        sa.Column("campaign_id", sa.Text(), nullable=True),
        sa.Column("user_ref", sa.Text(), nullable=True),
        sa.Column("reference_id", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.Text(), nullable=True),
        sa.Column("experiment_tag", sa.Text(), nullable=True),
        sa.Column("virtual_account_id", sa.Text(), nullable=True),
        sa.Column("bank_transfer_id", sa.Text(), nullable=True),
        sa.Column("collected_amount_paise", sa.BigInteger(), nullable=True),
        sa.Column("collection_mode", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_link_id", sa.Text(), nullable=True),
        sa.Column("payment_link_url", sa.Text(), nullable=True),
        sa.Column("payment_link_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("strategy_tag", sa.Text(), nullable=True),
        sa.Column("dunning_message_en", sa.Text(), nullable=True),
        sa.Column("dunning_message_hi", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_cases_merchant", "cases", ["merchant_id"])
    op.create_index("idx_cases_state", "cases", ["state"])
    op.create_index("idx_cases_arm", "cases", ["experiment_arm"])
    op.create_index("idx_cases_rail", "cases", ["payment_rail"])
    op.create_index("idx_cases_error", "cases", ["error_code"])
    op.create_index("idx_cases_customer", "cases", ["customer_id"])
    op.create_index("idx_cases_amount", "cases", ["amount_paise"])
    op.create_index("idx_cases_created", "cases", ["created_at"])
    op.create_index("idx_cases_occurred", "cases", ["occurred_at"])
    op.create_index("idx_cases_exp_tag", "cases", ["experiment_tag"])
    op.create_index("idx_cases_campaign", "cases", ["campaign_id"])
    op.create_index("idx_cases_user_ref", "cases", ["user_ref"])
    op.create_index("idx_cases_reference_id", "cases", ["reference_id"])

    # 2. Audit Table (Append-only immutable)
    op.create_table(
        "audit",
        sa.Column("entry_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "decision_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "decision_outputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "model_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "cost_incurred_paise", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_audit_case", "audit", ["case_id", "timestamp"])
    op.create_index("idx_audit_event", "audit", ["event_name"])
    op.create_index("idx_audit_timestamp", "audit", ["timestamp"])

    # 3. Idempotency Keys Table
    op.create_table(
        "idempotency_keys",
        sa.Column("idempotency_key", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_idempotency_case", "idempotency_keys", ["case_id"])

    # 4. Scheduled Jobs Table
    op.create_table(
        "jobs",
        sa.Column("job_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="QUEUED"),
        sa.Column("idempotency_key", sa.Text(), nullable=True, unique=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_jobs_due", "jobs", ["status", "due_at"])

    # 5. Model Telemetry Table
    op.create_table(
        "model_telemetry",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "success", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "used_fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("experiment_tag", sa.Text(), nullable=True),
        sa.Column(
            "config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("case_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_model_telemetry_model", "model_telemetry", ["model"])
    op.create_index("idx_model_telemetry_prov", "model_telemetry", ["provider"])
    op.create_index("idx_model_telemetry_exp", "model_telemetry", ["experiment_tag"])
    op.create_index("idx_model_telemetry_created", "model_telemetry", ["created_at"])

    # 6. Pattern Alerts Table
    op.create_table(
        "pattern_alerts",
        sa.Column("alert_id", sa.Text(), primary_key=True),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("feature_scope", sa.Text(), nullable=False),
        sa.Column("dominant_category", sa.Text(), nullable=True),
        sa.Column("dominant_intervention", sa.Text(), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("mean_amount_paise", sa.BigInteger(), nullable=False),
        sa.Column(
            "example_case_ids_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 7. ML Models Table
    op.create_table(
        "ml_models",
        sa.Column("model_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column(
            "artifact_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "feature_schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("train_arm", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column(
            "holdout_metrics_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 8. ML Predictions Table
    op.create_table(
        "ml_predictions",
        sa.Column("prediction_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prediction_type", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "inputs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 9. Workflows Table
    op.create_table(
        "workflows",
        sa.Column("workflow_id", sa.Text(), primary_key=True),
        sa.Column("case_id", sa.Text(), nullable=False, unique=True),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=False),
        sa.Column("recovery_state", sa.Text(), nullable=False),
        sa.Column(
            "context_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "stopping_rules_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "timers_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("touches_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_terminal", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("terminal_outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_workflows_case", "workflows", ["case_id"])
    op.create_index("idx_workflows_stage", "workflows", ["current_stage"])
    op.create_index("idx_workflows_template", "workflows", ["template"])

    # 10. Workflow Events Table
    op.create_table(
        "workflow_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_stage", sa.Text(), nullable=True),
        sa.Column("to_stage", sa.Text(), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column(
            "details_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("idx_workflow_events_wid", "workflow_events", ["workflow_id"])

    # 11. Workflow Signals Table
    op.create_table(
        "workflow_signals",
        sa.Column("signal_id", sa.Text(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Text(),
            sa.ForeignKey("workflows.workflow_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_workflow_signals_wid", "workflow_signals", ["workflow_id"])

    # 12. Workflow Template Definitions Table
    op.create_table(
        "workflow_template_definitions",
        sa.Column("template_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="published"),
        sa.Column("base_template", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column(
            "allowed_actions_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "stopping_rules_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "graph_nodes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "graph_edges_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 13. Operator Mode Table (single row singleton)
    op.create_table(
        "operator_mode",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_operator_mode_singleton"),
    )

    # 14. Merchant Policy Table
    op.create_table(
        "merchant_policy",
        sa.Column("merchant_id", sa.Text(), primary_key=True),
        sa.Column(
            "policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 15. LLM Settings Table (single row singleton)
    op.create_table(
        "llm_settings",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column(
            "settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_llm_settings_singleton"),
    )


def downgrade() -> None:
    op.drop_table("llm_settings")
    op.drop_table("merchant_policy")
    op.drop_table("operator_mode")
    op.drop_table("workflow_template_definitions")
    op.drop_table("workflow_signals")
    op.drop_table("workflow_events")
    op.drop_table("workflows")
    op.drop_table("ml_predictions")
    op.drop_table("ml_models")
    op.drop_table("pattern_alerts")
    op.drop_table("model_telemetry")
    op.drop_table("jobs")
    op.drop_table("idempotency_keys")
    op.drop_table("audit")
    op.drop_table("cases")
