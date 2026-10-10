"""ExecutionEngine — runs a single execution through all its policy stages.

Opens its own DB session; never called from within a request-scoped session.
All DB writes happen here; runtime/ is never imported with DB access.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import AgentVersion, AgentVersionTool, McpTool
from app.core.config import settings
from app.executions.models import Execution, ExecutionEvent, Message
from app.policies.models import Checkpoint, Policy, PolicyStage
from app.projects.models import Project  # noqa: F401 — ensures projects table is in mapper metadata
from app.runtime import StageError, run_stage
from app.work_items.models import WorkItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _persist_event(
    db: AsyncSession,
    execution_id: str,
    stage_id: str | None,
    event_type: str,
    actor_type: str,
    payload: dict,
) -> ExecutionEvent:
    ev = ExecutionEvent(
        id=uuid.uuid4(),
        execution_id=execution_id,
        stage_id=stage_id,
        event_type=event_type,
        actor_type=actor_type,
        payload=payload,
        created_at=_now(),
    )
    db.add(ev)
    return ev


class ExecutionEngine:
    def __init__(self, session_factory: Any | None = None) -> None:
        self._session_factory = session_factory

    def _get_session_factory(self):
        if self._session_factory is not None:
            return self._session_factory
        # Import lazily so that test reloads of app.core.db are respected
        from app.core.db import AsyncSessionLocal
        return AsyncSessionLocal

    async def run_execution(self, execution_id: str, start_from_stage_sequence: int = 1) -> None:
        async with self._get_session_factory()() as db:
            try:
                await self._run(db, execution_id, start_from_stage_sequence)
            except Exception:
                # Outer safety net — _run handles its own exceptions; this catches
                # anything that escapes (e.g. session-open failures).
                print(
                    f"[engine] unhandled error for execution {execution_id}",
                    file=sys.stderr,
                )

    async def _run(self, db: AsyncSession, execution_id: str, start_from_stage_sequence: int = 1) -> None:
        # ------------------------------------------------------------------
        # 1. Load execution
        # ------------------------------------------------------------------
        result = await db.execute(
            select(Execution).where(Execution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if execution is None:
            print(f"[engine] execution {execution_id} not found", file=sys.stderr)
            return

        # ------------------------------------------------------------------
        # 2. Load policy and stages
        # ------------------------------------------------------------------
        result = await db.execute(
            select(Policy).where(Policy.id == execution.policy_id)
        )
        policy = result.scalar_one()

        result = await db.execute(
            select(PolicyStage)
            .where(PolicyStage.policy_id == policy.id)
            .order_by(PolicyStage.sequence)
        )
        stages = list(result.scalars().all())

        result = await db.execute(
            select(Checkpoint).where(Checkpoint.policy_id == policy.id)
        )
        checkpoints = list(result.scalars().all())
        # Index by stage_id (str); final_review has stage_id=None
        checkpoint_by_stage: dict[str | None, Checkpoint] = {}
        final_review_checkpoint: Checkpoint | None = None
        for cp in checkpoints:
            if cp.stage_id is None:
                final_review_checkpoint = cp
            else:
                checkpoint_by_stage[str(cp.stage_id)] = cp

        result = await db.execute(
            select(WorkItem).where(WorkItem.id == execution.work_item_id)
        )
        work_item = result.scalar_one()

        # ------------------------------------------------------------------
        # 3. Transition to running
        # ------------------------------------------------------------------
        now = _now()
        execution.status = "running"
        execution.started_at = now
        execution.updated_at = now
        await _persist_event(
            db, execution_id, None,
            "execution.started", "system",
            {"execution_number": execution.execution_number},
        )
        await db.commit()

        total_stages = len(stages)

        try:
            # --------------------------------------------------------------
            # 4. Stage loop
            # --------------------------------------------------------------
            for stage in stages:
                if stage.sequence < start_from_stage_sequence:
                    continue
                sid = str(stage.id)
                now = _now()
                execution.current_stage_id = stage.id
                execution.updated_at = now

                # Load agent version + tools
                result = await db.execute(
                    select(AgentVersion).where(AgentVersion.id == stage.agent_version_id)
                )
                agent_version = result.scalar_one()

                result = await db.execute(
                    select(McpTool)
                    .join(AgentVersionTool, AgentVersionTool.mcp_tool_id == McpTool.id)
                    .where(AgentVersionTool.agent_version_id == agent_version.id)
                )
                tools = list(result.scalars().all())
                tool_names = [t.tool_name for t in tools]

                agent_definition = {
                    "name": agent_version.instructions[:60].replace(" ", "_"),
                    "instructions": agent_version.instructions,
                    "capabilities": agent_version.capabilities or [],
                }

                await _persist_event(
                    db, execution_id, sid,
                    "stage.started", "system",
                    {
                        "sequence": stage.sequence,
                        "name": stage.name,
                        "agent_name": agent_definition["name"],
                    },
                )
                await db.commit()

                # Compose task text (CONTRACTS.md D6)
                task_text = self._compose_task(
                    work_item, stage, total_stages
                )

                # Append previous stage outputs from this execution
                result = await db.execute(
                    select(Message)
                    .where(
                        Message.execution_id == execution_id,
                        Message.sender_type == "agent",
                        Message.message_type == "stage_output",
                    )
                    .order_by(Message.created_at)
                )
                prior_outputs = list(result.scalars().all())
                if prior_outputs:
                    task_text += "\n\nPrevious stage outputs:\n"
                    for msg in prior_outputs:
                        task_text += f"\n---\n{msg.content[:2000]}"

                # TODO(D7): inject knowledge block here

                # Consume pending human guidance
                result = await db.execute(
                    select(Message)
                    .where(
                        Message.execution_id == execution_id,
                        Message.sender_type == "human",
                        Message.consumed_at.is_(None),
                    )
                    .order_by(Message.created_at)
                )
                guidance_msgs = list(result.scalars().all())
                if guidance_msgs:
                    task_text += "\n\nHuman guidance:\n"
                    for gm in guidance_msgs:
                        task_text += f"\n{gm.content}"
                        gm.consumed_at = _now()
                        gm.updated_at = _now()

                # Run the stage
                async for event in run_stage(
                    agent_definition,
                    task_text,
                    tool_names,
                    timeout_seconds=settings.STAGE_TIMEOUT_SECONDS,
                ):
                    if event["event_type"] == "stage.stream_end":
                        # Persist stage output as a message
                        final_text = event["payload"]["final_text"]
                        now = _now()
                        msg = Message(
                            id=uuid.uuid4(),
                            execution_id=execution_id,
                            stage_id=stage.id,
                            sender_type="agent",
                            message_type="stage_output",
                            content=final_text,
                            created_at=now,
                            updated_at=now,
                        )
                        db.add(msg)
                        await db.commit()
                        break

                    # Persist the contract event; truncate agent.message to preview
                    payload = event["payload"]
                    if event["event_type"] == "agent.message":
                        payload = {"preview": event["payload"].get("text", "")[:500]}

                    await _persist_event(
                        db, execution_id, sid,
                        event["event_type"], "agent", payload,
                    )
                    await db.commit()

                # Stage completed
                await _persist_event(
                    db, execution_id, sid,
                    "stage.completed", "system",
                    {"sequence": stage.sequence},
                )
                await db.commit()

                # Check for a checkpoint on this stage
                cp = checkpoint_by_stage.get(sid)
                if cp is not None:
                    now = _now()
                    execution.status = "waiting_for_approval"
                    execution.blocking_checkpoint_id = cp.id
                    execution.updated_at = now
                    await _persist_event(
                        db, execution_id, sid,
                        "checkpoint.triggered", "system",
                        {
                            "checkpoint_id": str(cp.id),
                            "type": cp.type,
                            "assignee_name": str(cp.assigned_user_id),
                        },
                    )
                    await _persist_event(
                        db, execution_id, sid,
                        "execution.paused", "system",
                        {"reason": "checkpoint"},
                    )
                    await db.commit()
                    return  # Background task ends; resumes from checkpoint response

            # --------------------------------------------------------------
            # 5. All stages done
            # --------------------------------------------------------------
            now = _now()
            if final_review_checkpoint is not None:
                execution.status = "waiting_for_approval"
                execution.blocking_checkpoint_id = final_review_checkpoint.id
                execution.updated_at = now
                await _persist_event(
                    db, execution_id, None,
                    "checkpoint.triggered", "system",
                    {
                        "checkpoint_id": str(final_review_checkpoint.id),
                        "type": final_review_checkpoint.type,
                        "assignee_name": str(final_review_checkpoint.assigned_user_id),
                    },
                )
                await _persist_event(
                    db, execution_id, None,
                    "execution.paused", "system",
                    {"reason": "checkpoint"},
                )
                await db.commit()
            else:
                execution.status = "completed"
                execution.completed_at = now
                execution.blocking_checkpoint_id = None
                execution.updated_at = now
                work_item.status = "completed"
                work_item.updated_at = now
                await _persist_event(
                    db, execution_id, None,
                    "execution.completed", "system", {},
                )
                await db.commit()

        except StageError as e:
            now = _now()
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = now
            execution.updated_at = now
            await _persist_event(
                db, execution_id, None,
                "execution.failed", "system",
                {"error": str(e)},
            )
            await db.commit()

        except Exception as e:
            print(
                f"[engine] unexpected error for execution {execution_id}: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            now = _now()
            execution.status = "failed"
            execution.error = "internal engine error"
            execution.completed_at = now
            execution.updated_at = now
            await _persist_event(
                db, execution_id, None,
                "execution.failed", "system",
                {"error": "internal engine error"},
            )
            await db.commit()

    @staticmethod
    def _compose_task(work_item: WorkItem, stage: PolicyStage, total: int) -> str:
        parts = [
            f"Work item: {work_item.objective}\n{work_item.description}\n"
            f"Expected outcome: {work_item.expected_outcome}",
            f"You are performing stage {stage.sequence} of {total}: {stage.name}\n"
            f"{stage.description}\nExpected output: {stage.expected_output}",
        ]
        return "\n\n".join(parts)
