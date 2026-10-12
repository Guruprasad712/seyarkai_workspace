"""initial schema — 17 tables

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sequence for agent_code formatting (agent-0001, agent-0002, …)
    op.execute("CREATE SEQUENCE agent_code_seq START 1")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.VARCHAR(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("hashed_password", sa.VARCHAR(), nullable=False),
        sa.Column("role", sa.VARCHAR(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_code", sa.VARCHAR(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("role_purpose", sa.VARCHAR(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_code"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "agent_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.VARCHAR(), nullable=False),
        sa.Column("instructions", sa.TEXT(), nullable=False),
        sa.Column("capabilities", JSONB(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_versions_agent_id", "agent_versions", ["agent_id"])

    op.create_table(
        "mcp_tools",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("tool_name", sa.VARCHAR(), nullable=False),
        sa.Column("server_key", sa.VARCHAR(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tool_name"),
    )

    op.create_table(
        "agent_version_tools",
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("mcp_tool_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["mcp_tool_id"], ["mcp_tools.id"]),
        sa.PrimaryKeyConstraint("agent_version_id", "mcp_tool_id"),
    )
    op.create_index("ix_agent_version_tools_agent_version_id",
                    "agent_version_tools", ["agent_version_id"])
    op.create_index("ix_agent_version_tools_mcp_tool_id",
                    "agent_version_tools", ["mcp_tool_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_created_by", "projects", ["created_by"])

    op.create_table(
        "work_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("objective", sa.TEXT(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("expected_outcome", sa.TEXT(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_items_project_id", "work_items", ["project_id"])
    op.create_index("ix_work_items_created_by", "work_items", ["created_by"])

    op.create_table(
        "work_item_workers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_item_id", sa.UUID(), nullable=False),
        sa.Column("worker_type", sa.VARCHAR(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(worker_type = 'ai_agent' AND agent_version_id IS NOT NULL AND user_id IS NULL)"
            " OR "
            "(worker_type = 'human' AND user_id IS NOT NULL AND agent_version_id IS NULL)",
            name="ck_work_item_workers_type_fk",
        ),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_item_workers_work_item_id",
                    "work_item_workers", ["work_item_id"])
    op.create_index("ix_work_item_workers_agent_version_id",
                    "work_item_workers", ["agent_version_id"])
    op.create_index("ix_work_item_workers_user_id",
                    "work_item_workers", ["user_id"])

    op.create_table(
        "policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_item_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("generated_by", sa.VARCHAR(), nullable=False),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policies_work_item_id", "policies", ["work_item_id"])
    op.create_index("ix_policies_published_by", "policies", ["published_by"])

    op.create_table(
        "policy_stages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("expected_output", sa.TEXT(), nullable=False),
        sa.Column("agent_version_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_stages_policy_id", "policy_stages", ["policy_id"])
    op.create_index("ix_policy_stages_agent_version_id",
                    "policy_stages", ["agent_version_id"])

    op.create_table(
        "checkpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=True),
        sa.Column("type", sa.VARCHAR(), nullable=False),
        sa.Column("assigned_user_id", sa.UUID(), nullable=False),
        sa.Column("instruction", sa.TEXT(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["policy_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checkpoints_policy_id", "checkpoints", ["policy_id"])
    op.create_index("ix_checkpoints_stage_id", "checkpoints", ["stage_id"])
    op.create_index("ix_checkpoints_assigned_user_id",
                    "checkpoints", ["assigned_user_id"])

    op.create_table(
        "executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_item_id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("execution_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.VARCHAR(), nullable=False),
        sa.Column("current_stage_id", sa.UUID(), nullable=True),
        sa.Column("blocking_checkpoint_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.TEXT(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["blocking_checkpoint_id"], ["checkpoints.id"]),
        sa.ForeignKeyConstraint(["current_stage_id"], ["policy_stages.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"]),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_executions_work_item_id", "executions", ["work_item_id"])
    op.create_index("ix_executions_policy_id", "executions", ["policy_id"])
    op.create_index("ix_executions_current_stage_id",
                    "executions", ["current_stage_id"])
    op.create_index("ix_executions_blocking_checkpoint_id",
                    "executions", ["blocking_checkpoint_id"])

    # Append-only; no updated_at
    op.create_table(
        "execution_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.VARCHAR(), nullable=False),
        sa.Column("actor_type", sa.VARCHAR(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["policy_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_events_execution_id",
                    "execution_events", ["execution_id"])
    op.create_index("ix_execution_events_stage_id",
                    "execution_events", ["stage_id"])
    # Composite index required by D1
    op.create_index("ix_execution_events_execution_id_created_at",
                    "execution_events", ["execution_id", "created_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=True),
        sa.Column("sender_type", sa.VARCHAR(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=True),
        sa.Column("message_type", sa.VARCHAR(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["policy_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_execution_id", "messages", ["execution_id"])
    op.create_index("ix_messages_stage_id", "messages", ["stage_id"])

    op.create_table(
        "checkpoint_responses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("checkpoint_id", sa.UUID(), nullable=False),
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("responded_by", sa.UUID(), nullable=False),
        sa.Column("decision", sa.VARCHAR(), nullable=False),
        sa.Column("comment", sa.TEXT(), nullable=True),
        sa.Column("input", JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"]),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["responded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_checkpoint_responses_checkpoint_id",
                    "checkpoint_responses", ["checkpoint_id"])
    op.create_index("ix_checkpoint_responses_execution_id",
                    "checkpoint_responses", ["execution_id"])
    op.create_index("ix_checkpoint_responses_responded_by",
                    "checkpoint_responses", ["responded_by"])

    # Append-only; no updated_at
    op.create_table(
        "artifacts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("stage_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.VARCHAR(), nullable=False),
        sa.Column("type", sa.VARCHAR(), nullable=False),
        sa.Column("url", sa.VARCHAR(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["stage_id"], ["policy_stages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_artifacts_execution_id", "artifacts", ["execution_id"])
    op.create_index("ix_artifacts_stage_id", "artifacts", ["stage_id"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.VARCHAR(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("source", sa.VARCHAR(), nullable=False),
        sa.Column("last_verified_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("verified_by", sa.UUID(), nullable=True),
        sa.Column("external_id", sa.VARCHAR(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_verified_by",
                    "knowledge_documents", ["verified_by"])


def downgrade() -> None:
    op.drop_table("knowledge_documents")
    op.drop_table("artifacts")
    op.drop_table("checkpoint_responses")
    op.drop_table("messages")
    op.drop_table("execution_events")
    op.drop_table("executions")
    op.drop_table("checkpoints")
    op.drop_table("policy_stages")
    op.drop_table("policies")
    op.drop_table("work_item_workers")
    op.drop_table("work_items")
    op.drop_table("projects")
    op.drop_table("agent_version_tools")
    op.drop_table("mcp_tools")
    op.drop_table("agent_versions")
    op.drop_table("agents")
    op.drop_table("users")
    op.execute("DROP SEQUENCE agent_code_seq")
