"use client"

import { use, useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Loader2 } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import type {
  CheckpointBrief,
  EventOut,
  ExecutionOut,
  ExecutionSummaryOut,
  PolicyOut,
  StageSummary,
  WorkItem,
} from "@/lib/types"

// ─── Constants ────────────────────────────────────────────────────────────────

const TERMINAL = new Set(["completed", "failed"])
const STATUS_POLL_MS = 3000
const EVENT_POLL_MS = 2000

// ─── Helpers ─────────────────────────────────────────────────────────────────

const statusColors: Record<string, string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  waiting_for_approval: "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
}

function StatusBadge({ status }: { status: string }) {
  const cls = statusColors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status.replace(/_/g, " ")}
    </span>
  )
}

const actorColors: Record<string, string> = {
  system: "bg-muted text-muted-foreground",
  agent: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  human: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
}

function ActorBadge({ actor }: { actor: string }) {
  const cls = actorColors[actor] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium shrink-0 ${cls}`}>
      {actor}
    </span>
  )
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function describeEvent(ev: EventOut): string {
  const p = ev.payload
  switch (ev.event_type) {
    case "execution.started":
      return `Execution #${p.execution_number} started`
    case "stage.started":
      return `Stage ${p.sequence} — ${p.name}`
    case "tool.called":
      return `Tool called: ${p.tool_name}`
    case "tool.result": {
      const summary = String(p.summary ?? "")
      return `Tool result: ${summary.length > 100 ? summary.slice(0, 100) + "…" : summary}`
    }
    case "agent.message": {
      const preview = String(p.preview ?? "")
      return `Agent: ${preview.length > 120 ? preview.slice(0, 120) + "…" : preview}`
    }
    case "stage.completed":
      return `Stage ${p.sequence} completed`
    case "checkpoint.triggered":
      return `Checkpoint reached — ${p.type}`
    case "execution.paused":
      return "Execution paused"
    case "checkpoint.resolved":
      return `Checkpoint ${p.decision}`
    case "execution.resumed":
      return "Execution resumed"
    case "execution.completed":
      return "Execution completed"
    case "agent.summary": {
      const s = String(p.summary ?? "")
      return `Summary: ${s.length > 120 ? s.slice(0, 120) + "…" : s}`
    }
    case "execution.failed":
      return `Failed: ${p.error}`
    default:
      return ev.event_type
  }
}

// ─── Checkpoint Action Panel ──────────────────────────────────────────────────

function CheckpointActions({
  executionId,
  checkpoint,
  onResponse,
}: {
  executionId: string
  checkpoint: CheckpointBrief
  onResponse: (nextAction: string, newStatus: string) => void
}) {
  const [inputText, setInputText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  async function respond(decision: string, comment?: string, input?: string) {
    setError("")
    setSubmitting(true)
    try {
      const res = await apiFetch<{ execution_id: string; status: string; next_action: string }>(
        `/executions/${executionId}/checkpoints/${checkpoint.id}/respond`,
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            ...(comment ? { comment } : {}),
            ...(input ? { input_text: input } : {}),
          }),
        }
      )
      onResponse(res.next_action, res.status)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit response")
    } finally {
      setSubmitting(false)
    }
  }

  const type = checkpoint.type

  return (
    <div className="mt-3 space-y-2">
      {type === "input" ? (
        <>
          <textarea
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            rows={3}
            placeholder="Enter your input…"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={submitting}
          />
          <Button
            size="sm"
            disabled={submitting || !inputText.trim()}
            onClick={() => respond("input_provided", undefined, inputText.trim())}
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Submit"}
          </Button>
        </>
      ) : type === "final_review" ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={submitting}
            onClick={() => respond("approve")}
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Complete ✓"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={submitting}
            onClick={() => respond("reject")}
          >
            Rework
          </Button>
        </div>
      ) : type === "review" ? (
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={submitting}
            onClick={() => respond("approve")}
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Accept"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={submitting}
            onClick={() => respond("reject")}
          >
            Request Changes
          </Button>
        </div>
      ) : (
        /* approval (default) */
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={submitting}
            onClick={() => respond("approve")}
          >
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Approve"}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={submitting}
            onClick={() => respond("reject")}
          >
            Reject
          </Button>
        </div>
      )}
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  )
}

// ─── Summary View ─────────────────────────────────────────────────────────────

function DecisionBadge({ decision }: { decision: string }) {
  const approved = decision === "approve"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
      approved
        ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
        : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
    }`}>
      {approved ? "Approved" : "Rejected"}
    </span>
  )
}

function StageSummaryCard({ stage }: { stage: StageSummary }) {
  return (
    <div className="rounded-lg border border-border overflow-hidden">
      {/* Stage header */}
      <div className="flex items-center gap-3 bg-muted/40 px-5 py-3 border-b border-border">
        <span className="text-xs font-medium text-muted-foreground">STAGE {stage.sequence}</span>
        <span className="text-sm font-semibold">{stage.name}</span>
        {stage.checkpoint_decision && (
          <span className="ml-auto"><DecisionBadge decision={stage.checkpoint_decision} /></span>
        )}
      </div>

      <div className="divide-y divide-border">
        {/* Task */}
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Task Description</p>
          <p className="text-sm whitespace-pre-wrap text-foreground">{stage.description}</p>
        </div>

        {/* Expected output */}
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Expected Output</p>
          <p className="text-sm whitespace-pre-wrap text-muted-foreground">{stage.expected_output}</p>
        </div>

        {/* Agent output */}
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Agent Output</p>
          {stage.agent_output ? (
            <p className="text-sm whitespace-pre-wrap text-foreground">{stage.agent_output}</p>
          ) : (
            <p className="text-sm italic text-muted-foreground">No output recorded.</p>
          )}
        </div>

        {/* Checkpoint review */}
        {stage.checkpoint_type && (
          <div className="px-5 py-4 bg-muted/20">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Checkpoint — {stage.checkpoint_type.replace(/_/g, " ")}
            </p>
            {stage.checkpoint_decision ? (
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <DecisionBadge decision={stage.checkpoint_decision} />
                </div>
                {stage.checkpoint_comment && (
                  <p className="text-sm text-foreground mt-2 whitespace-pre-wrap">{stage.checkpoint_comment}</p>
                )}
              </div>
            ) : (
              <p className="text-sm italic text-muted-foreground">No response recorded.</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryView({ summary, status }: { summary: ExecutionSummaryOut; status: string }) {
  const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString() : "—"
  const duration = summary.started_at && summary.completed_at
    ? Math.round((new Date(summary.completed_at).getTime() - new Date(summary.started_at).getTime()) / 1000)
    : null

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-8 space-y-8">

        {/* Overview card */}
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="bg-muted/40 px-5 py-3 border-b border-border">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Execution Overview</p>
          </div>
          <div className="divide-y divide-border">
            <div className="px-5 py-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Status</p>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                  status === "completed"
                    ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                }`}>{status}</span>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Started</p>
                <p className="text-sm">{fmt(summary.started_at)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Completed</p>
                <p className="text-sm">{fmt(summary.completed_at)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground mb-0.5">Duration</p>
                <p className="text-sm">{duration !== null ? `${duration}s` : "—"}</p>
              </div>
            </div>

            {summary.error && (
              <div className="px-5 py-4 bg-destructive/5">
                <p className="text-xs font-semibold uppercase tracking-wide text-destructive mb-1">Error</p>
                <p className="text-sm text-destructive">{summary.error}</p>
              </div>
            )}
          </div>
        </div>

        {/* Work item */}
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="bg-muted/40 px-5 py-3 border-b border-border">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Work Item</p>
          </div>
          <div className="divide-y divide-border">
            <div className="px-5 py-4">
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Objective</p>
              <p className="text-sm text-foreground">{summary.work_item_objective}</p>
            </div>
            <div className="px-5 py-4">
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Description</p>
              <p className="text-sm whitespace-pre-wrap text-foreground">{summary.work_item_description}</p>
            </div>
            <div className="px-5 py-4">
              <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Expected Outcome</p>
              <p className="text-sm whitespace-pre-wrap text-foreground">{summary.work_item_expected_outcome}</p>
            </div>
          </div>
        </div>

        {/* Stages */}
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Stages ({summary.stages.length})
          </p>
          <div className="space-y-4">
            {summary.stages.map((s) => (
              <StageSummaryCard key={s.sequence} stage={s} />
            ))}
          </div>
        </div>

        {/* Final review */}
        {(summary.final_review_decision || summary.final_review_comment) && (
          <div className="rounded-lg border border-border overflow-hidden">
            <div className="bg-muted/40 px-5 py-3 border-b border-border flex items-center gap-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Final Review</p>
              {summary.final_review_decision && <DecisionBadge decision={summary.final_review_decision} />}
            </div>
            {summary.final_review_comment && (
              <div className="px-5 py-4">
                <p className="text-sm whitespace-pre-wrap text-foreground">{summary.final_review_comment}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ExecutionWorkspacePage({
  params,
}: {
  params: Promise<{ executionId: string }>
}) {
  const { executionId } = use(params)
  const { user } = useAuth()

  const [execution, setExecution] = useState<ExecutionOut | null>(null)
  const [workItem, setWorkItem] = useState<WorkItem | null>(null)
  const [policy, setPolicy] = useState<PolicyOut | null>(null)
  const [events, setEvents] = useState<EventOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [activeTab, setActiveTab] = useState<"timeline" | "summary">("timeline")
  const [summary, setSummary] = useState<ExecutionSummaryOut | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)

  const lastEventIdRef = useRef<string | null>(null)
  const timelineRef = useRef<HTMLDivElement>(null)
  const statusPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const eventPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Initial load ─────────────────────────────────────────────────────────

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [exec, initialEvents] = await Promise.all([
        apiFetch<ExecutionOut>(`/executions/${executionId}`),
        apiFetch<EventOut[]>(`/executions/${executionId}/events`),
      ])
      setExecution(exec)
      setEvents(initialEvents)
      if (initialEvents.length > 0) {
        lastEventIdRef.current = initialEvents[initialEvents.length - 1].id
      }
      // Fetch work item for back link
      apiFetch<WorkItem>(`/work-items/${exec.work_item_id}`)
        .then(setWorkItem)
        .catch(() => {})
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load execution")
    } finally {
      setLoading(false)
    }
  }, [executionId])

  useEffect(() => {
    loadInitial()
  }, [loadInitial])

  // ── Load policy once policy_id is known ──────────────────────────────────

  useEffect(() => {
    if (!execution?.policy_id || policy?.id === execution.policy_id) return
    apiFetch<PolicyOut>(`/policies/${execution.policy_id}`)
      .then(setPolicy)
      .catch(() => {})
  }, [execution?.policy_id, policy?.id])

  // ── Status polling ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!execution || TERMINAL.has(execution.status)) {
      if (statusPollRef.current) {
        clearInterval(statusPollRef.current)
        statusPollRef.current = null
      }
      return
    }

    statusPollRef.current = setInterval(async () => {
      try {
        const updated = await apiFetch<ExecutionOut>(`/executions/${executionId}`)
        setExecution(updated)
        if (TERMINAL.has(updated.status)) {
          clearInterval(statusPollRef.current!)
          statusPollRef.current = null
        }
      } catch {
        // network hiccup — keep polling
      }
    }, STATUS_POLL_MS)

    return () => {
      if (statusPollRef.current) {
        clearInterval(statusPollRef.current)
        statusPollRef.current = null
      }
    }
  }, [execution?.id, execution?.status, executionId])

  // ── Event polling ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!execution || TERMINAL.has(execution.status)) {
      // Do one final poll on terminal to catch last events, then stop
      if (execution && TERMINAL.has(execution.status)) {
        const afterParam = lastEventIdRef.current ? `?after=${lastEventIdRef.current}&limit=100` : "?limit=100"
        apiFetch<EventOut[]>(`/executions/${executionId}/events${afterParam}`)
          .then((newEvs) => {
            if (newEvs.length > 0) {
              setEvents((prev) => [...prev, ...newEvs])
              lastEventIdRef.current = newEvs[newEvs.length - 1].id
            }
          })
          .catch(() => {})
      }
      if (eventPollRef.current) {
        clearInterval(eventPollRef.current)
        eventPollRef.current = null
      }
      return
    }

    eventPollRef.current = setInterval(async () => {
      const afterParam = lastEventIdRef.current ? `?after=${lastEventIdRef.current}&limit=100` : "?limit=100"
      try {
        const newEvs = await apiFetch<EventOut[]>(`/executions/${executionId}/events${afterParam}`)
        if (newEvs.length > 0) {
          setEvents((prev) => [...prev, ...newEvs])
          lastEventIdRef.current = newEvs[newEvs.length - 1].id
        }
      } catch {
        // network hiccup — keep polling
      }
    }, EVENT_POLL_MS)

    return () => {
      if (eventPollRef.current) {
        clearInterval(eventPollRef.current)
        eventPollRef.current = null
      }
    }
  }, [execution?.id, execution?.status, executionId])

  // ── Auto-scroll timeline ──────────────────────────────────────────────────

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight
    }
  }, [events])

  // ── Checkpoint response handler ───────────────────────────────────────────

  async function loadSummary() {
    if (summaryLoading || summary) return
    setSummaryLoading(true)
    try {
      const s = await apiFetch<ExecutionSummaryOut>(`/executions/${executionId}/summary`)
      setSummary(s)
    } catch {
      // summary is best-effort; timeline remains available
    } finally {
      setSummaryLoading(false)
    }
  }

  function handleCheckpointResponse(nextAction: string, newStatus: string) {
    setExecution((prev) => prev ? { ...prev, status: newStatus, blocking_checkpoint: null } : prev)
    // Event poll will pick up the new events on next tick
  }

  // ─────────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-6 py-10 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading…
      </div>
    )
  }

  if (error || !execution) {
    return (
      <div className="px-6 py-10">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error || "Execution not found"}
        </div>
        <div className="mt-4">
          <Link href="/" className="text-sm text-muted-foreground hover:text-foreground">
            ← Dashboard
          </Link>
        </div>
      </div>
    )
  }

  const currentStage = policy?.stages.find((s) => s.id === execution.current_stage_id)
  const totalStages = policy?.stages.length ?? 0
  const cp = execution.blocking_checkpoint
  const isAssignee =
    cp !== null &&
    (user?.id === cp.assigned_user_id || user?.role === "super_admin")

  const backHref = workItem?.project_id
    ? `/projects/${workItem.project_id}/work-items/${execution.work_item_id}`
    : "/"

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3 shrink-0">
        <div className="flex items-center gap-4">
          <Link href={backHref} className="text-sm text-muted-foreground hover:text-foreground">
            ← {workItem?.name ?? "Work Item"}
          </Link>
          <span className="text-sm font-medium">
            Execution #{execution.execution_number}
          </span>
          <StatusBadge status={execution.status} />
        </div>
        <div className="flex items-center gap-3">
          {TERMINAL.has(execution.status) && (
            <div className="flex items-center rounded-md border border-border text-xs overflow-hidden">
              <button
                className={`px-3 py-1.5 transition-colors ${activeTab === "timeline" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}
                onClick={() => setActiveTab("timeline")}
              >
                Timeline
              </button>
              <button
                className={`px-3 py-1.5 transition-colors ${activeTab === "summary" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}
                onClick={() => { setActiveTab("summary"); loadSummary() }}
              >
                Summary
              </button>
            </div>
          )}
          {!TERMINAL.has(execution.status) && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Live
            </div>
          )}
        </div>
      </div>

      {/* Summary view */}
      {activeTab === "summary" && TERMINAL.has(execution.status) && (
        summaryLoading ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading summary…
          </div>
        ) : summary ? (
          <SummaryView summary={summary} status={execution.status} />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Summary unavailable.
          </div>
        )
      )}

      {/* Three-column workspace */}
      <div className={`grid flex-1 overflow-hidden lg:grid-cols-[280px_1fr_300px] ${activeTab === "summary" ? "hidden" : ""}`}>

        {/* LEFT — Stage info */}
        <div className="flex flex-col gap-4 border-r border-border overflow-y-auto px-4 py-5">
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-3">CURRENT STAGE</p>
            {execution.status === "queued" ? (
              <p className="text-sm text-muted-foreground">Waiting to start…</p>
            ) : !currentStage ? (
              <p className="text-sm text-muted-foreground">
                {execution.current_stage_id ? "Loading…" : "–"}
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Stage {currentStage.sequence}{totalStages > 0 ? ` of ${totalStages}` : ""}
                </p>
                <p className="text-sm font-semibold">{currentStage.name}</p>
                {currentStage.description && (
                  <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                    {currentStage.description.length > 200
                      ? currentStage.description.slice(0, 200) + "…"
                      : currentStage.description}
                  </p>
                )}
              </div>
            )}
          </div>

          {execution.status === "failed" && execution.error && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5">
              <p className="text-xs font-medium text-destructive mb-1">Error</p>
              <p className="text-xs text-destructive">{execution.error}</p>
            </div>
          )}

          {execution.started_at && (
            <div className="mt-auto pt-4 border-t border-border">
              <p className="text-xs text-muted-foreground">
                Started {new Date(execution.started_at).toLocaleString()}
              </p>
              {execution.completed_at && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  Completed {new Date(execution.completed_at).toLocaleString()}
                </p>
              )}
            </div>
          )}
        </div>

        {/* CENTER — Events timeline */}
        <div className="flex flex-col border-r border-border overflow-hidden">
          <div className="shrink-0 border-b border-border px-4 py-2.5">
            <p className="text-xs font-medium text-muted-foreground">
              EVENTS {events.length > 0 && <span className="font-normal">({events.length})</span>}
            </p>
          </div>
          <div ref={timelineRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
            {events.length === 0 ? (
              <p className="text-xs text-muted-foreground">No events yet.</p>
            ) : (
              events.map((ev) => (
                <div key={ev.id} className="flex items-start gap-2 py-1">
                  <span className="text-xs tabular-nums text-muted-foreground shrink-0 mt-0.5 w-20">
                    {fmtTime(ev.created_at)}
                  </span>
                  <ActorBadge actor={ev.actor_type} />
                  <span className="text-xs text-foreground leading-relaxed">
                    {describeEvent(ev)}
                  </span>
                </div>
              ))
            )}
            {!TERMINAL.has(execution.status) && (
              <div className="flex items-center gap-1.5 py-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Waiting for updates…
              </div>
            )}
          </div>
        </div>

        {/* RIGHT — Checkpoint panel */}
        <div className="overflow-y-auto px-4 py-5">
          <p className="text-xs font-medium text-muted-foreground mb-3">CHECKPOINT</p>

          {cp ? (
            <div className="space-y-3">
              <div className="rounded-md border border-purple-200 bg-purple-50 px-3 py-2.5 dark:border-purple-800/40 dark:bg-purple-900/20">
                <p className="text-xs font-medium text-purple-800 dark:text-purple-300 mb-1">
                  ⏸ Waiting for {cp.type.replace(/_/g, " ")}
                </p>
                <p className="text-sm text-purple-900 dark:text-purple-200">
                  {cp.instruction}
                </p>
              </div>

              <div>
                <p className="text-xs text-muted-foreground">Assigned to</p>
                <p className="text-xs font-mono text-foreground mt-0.5 break-all">
                  {cp.assigned_user_id}
                </p>
              </div>

              {/* Agent summary */}
              <div className="rounded-md bg-gray-100 dark:bg-gray-800/50 px-3 py-2.5">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Agent Summary
                </p>
                {execution.pending_summary ? (
                  <p className="text-sm whitespace-pre-wrap">{execution.pending_summary}</p>
                ) : (
                  <p className="text-sm italic text-muted-foreground">Summary pending…</p>
                )}
              </div>

              {isAssignee ? (
                <CheckpointActions
                  executionId={executionId}
                  checkpoint={cp}
                  onResponse={handleCheckpointResponse}
                />
              ) : (
                <p className="text-xs text-muted-foreground">
                  You are not the assigned reviewer.
                </p>
              )}
            </div>
          ) : TERMINAL.has(execution.status) ? null : (
            <p className="text-xs text-muted-foreground">No checkpoint pending.</p>
          )}
        </div>
      </div>
    </div>
  )
}
