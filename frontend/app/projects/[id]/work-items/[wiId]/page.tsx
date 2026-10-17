"use client"

import { use, useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { StatusPill } from "@/components/status-pill"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import type { ExecutionOut, PolicyOut, WorkItem } from "@/lib/types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins} min ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.floor(hours / 24)} d ago`
}

const TERMINAL = new Set(["completed", "failed"])
const POLL_MS = 3000

type GenerateResult =
  | { kind: "draft_exists"; policyId: string }
  | { kind: "failures"; messages: string[] }
  | { kind: "error"; message: string }

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WorkItemDetailPage({
  params,
}: {
  params: Promise<{ id: string; wiId: string }>
}) {
  const { id: projectId, wiId } = use(params)
  const router = useRouter()
  const { user } = useAuth()
  const canEditPolicy = can.editPolicy(user?.role ?? "")
  const canExecute = can.execute(user?.role ?? "")

  const [workItem, setWorkItem]           = useState<WorkItem | null>(null)
  const [loading, setLoading]             = useState(true)
  const [error, setError]                 = useState("")
  const [generating, setGenerating]       = useState(false)
  const [generateResult, setGenerateResult] = useState<GenerateResult | null>(null)
  const [execution, setExecution]         = useState<ExecutionOut | null>(null)
  const [policy, setPolicy]               = useState<PolicyOut | null>(null)
  const [publishedPolicy, setPublishedPolicy] = useState<PolicyOut | null>(null)
  const [draftPolicy, setDraftPolicy]     = useState<PolicyOut | null>(null)
  const [executing, setExecuting]         = useState(false)
  const [executeError, setExecuteError]   = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [wi, execs, policies] = await Promise.all([
        apiFetch<WorkItem>(`/work-items/${wiId}`),
        apiFetch<ExecutionOut[]>(`/work-items/${wiId}/executions`).catch(() => [] as ExecutionOut[]),
        apiFetch<PolicyOut[]>(`/work-items/${wiId}/policies`).catch(() => [] as PolicyOut[]),
      ])
      setWorkItem(wi)
      if (execs.length > 0) setExecution(execs[execs.length - 1])
      const pub = policies.filter((p) => p.status === "published").sort((a, b) => b.version - a.version)[0] ?? null
      setPublishedPolicy(pub)
      const draft = policies.find((p) => p.status === "draft") ?? null
      setDraftPolicy(draft)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load work item")
    } finally {
      setLoading(false)
    }
  }, [wiId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!execution?.policy_id || policy?.id === execution.policy_id) return
    apiFetch<PolicyOut>(`/policies/${execution.policy_id}`)
      .then(setPolicy)
      .catch(() => {})
  }, [execution?.policy_id, policy?.id])

  useEffect(() => {
    if (!execution || TERMINAL.has(execution.status)) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
      return
    }
    pollRef.current = setInterval(async () => {
      try {
        const updated = await apiFetch<ExecutionOut>(`/executions/${execution.id}`)
        setExecution(updated)
        if (TERMINAL.has(updated.status) && pollRef.current) {
          clearInterval(pollRef.current); pollRef.current = null
          apiFetch<WorkItem>(`/work-items/${wiId}`).then(setWorkItem).catch(() => {})
        }
      } catch { /* keep polling */ }
    }, POLL_MS)
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [execution?.id, execution?.status, wiId])

  async function handleGeneratePolicy() {
    setGenerateResult(null)
    setGenerating(true)
    try {
      const pol = await apiFetch<{ id: string }>(`/work-items/${wiId}/policies/generate`, { method: "POST" })
      router.push(`/policies/${pol.id}?projectId=${projectId}&wiId=${wiId}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = (err.body as { detail?: { policy_id?: string } } | null)?.detail
        const policyId = detail?.policy_id ?? ""
        setGenerateResult({ kind: "draft_exists", policyId })
      } else if (err instanceof ApiError && err.status === 422) {
        const failures = extractPublishFailures(err.body)
        if (failures && failures.length > 0) {
          setGenerateResult({ kind: "failures", messages: failures.map((f) => f.message) })
        } else {
          setGenerateResult({ kind: "error", message: err.message })
        }
      } else {
        setGenerateResult({ kind: "error", message: err instanceof ApiError ? err.message : "Generation failed" })
      }
    } finally {
      setGenerating(false)
    }
  }

  async function handleExecute() {
    setExecuteError("")
    setExecuting(true)
    try {
      const res = await apiFetch<{ execution_id: string }>(`/work-items/${wiId}/executions`, { method: "POST" })
      router.push(`/executions/${res.execution_id}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setExecuteError("An execution is already running for this work item.")
      } else if (err instanceof ApiError && err.status === 422) {
        const detail = (err.body as Record<string, unknown> | null)?.detail
        const errorCode = typeof detail === "object" && detail !== null
          ? (detail as Record<string, unknown>).error : null
        if (errorCode === "no_published_policy") {
          setExecuteError("No published policy — generate and publish a policy before starting an execution.")
        } else {
          setExecuteError(err.message)
        }
      } else {
        setExecuteError(err instanceof ApiError ? err.message : "Failed to start execution")
      }
    } finally {
      setExecuting(false)
    }
  }

  if (loading) return <InlineLoader label="Loading work item…" />

  if (error || !workItem) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10">
        <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
          {error || "Work item not found"}
        </div>
        <Link href={`/projects/${projectId}`} className="mt-4 inline-block text-sm text-white/45 hover:text-white transition-colors">
          ← Back to project
        </Link>
      </div>
    )
  }

  const hasAiWorker = workItem.workers.some((w) => w.type === "ai_agent")
  const currentStage = policy?.stages.find((s) => s.id === execution?.current_stage_id)

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-4xl px-4 py-10">
        <Link href={`/projects/${projectId}`} className="text-sm text-white/45 hover:text-white transition-colors">
          ← {projectId ? "Project" : "Projects"}
        </Link>

        {/* Header */}
        <div className="mt-6 mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-heading text-3xl font-black text-white">{workItem.name}</h1>
              <StatusPill status={workItem.status} />
            </div>
            <p className="mt-1 text-sm text-white/45">One objective. One agent. Your whole team.</p>
            <p className="mt-1 font-mono text-xs text-white/30">
              Created {new Date(workItem.created_at).toLocaleDateString()}
            </p>
          </div>

          {/* Actions */}
          <div className="flex shrink-0 flex-col items-end gap-2">
            {hasAiWorker && canEditPolicy && (
              <BigButton variant="ghost" size="md" loading={generating} onClick={handleGeneratePolicy}>
                ✦ Generate Policy
              </BigButton>
            )}
            {workItem.status !== "completed" && canExecute && (
              <BigButton variant="gradient" size="md" loading={executing} onClick={handleExecute}>
                ▶ Execute
              </BigButton>
            )}
          </div>
        </div>

        {/* Execute error */}
        {executeError && (
          <div className={`mb-6 rounded-xl px-4 py-3 text-sm border ${
            executeError.startsWith("An execution is already")
              ? "bg-[#F59E0B]/10 border-[#F59E0B]/25 text-[#F59E0B]"
              : "bg-[#EF4444]/10 border-[#EF4444]/25 text-[#EF4444]"
          }`}>
            {executeError}
          </div>
        )}

        {/* Generate result banners */}
        {generateResult && (
          <div className="mb-6">
            {generateResult.kind === "draft_exists" && (
              <div className="rounded-xl bg-[#F59E0B]/10 border border-[#F59E0B]/25 px-4 py-3 text-sm text-[#F59E0B] flex items-center justify-between gap-3">
                <span>A draft policy already exists for this work item.</span>
                {generateResult.policyId && (
                  <Link
                    href={`/policies/${generateResult.policyId}?projectId=${projectId}&wiId=${wiId}`}
                    className="shrink-0 font-semibold underline underline-offset-2 hover:opacity-80 transition-opacity"
                  >
                    View draft →
                  </Link>
                )}
              </div>
            )}
            {generateResult.kind === "failures" && (
              <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3">
                <p className="mb-1 text-xs font-bold text-[#EF4444]">Generation validation failed</p>
                <ul className="space-y-0.5">
                  {generateResult.messages.map((m, i) => (
                    <li key={i} className="text-xs text-[#EF4444]/85">{m}</li>
                  ))}
                </ul>
              </div>
            )}
            {generateResult.kind === "error" && (
              <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
                Generation failed — {generateResult.message}
              </div>
            )}
          </div>
        )}

        {/* 2-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-5">
          {/* Left: Work item fields */}
          <div className="space-y-4">
            {[
              { label: "Objective",        value: workItem.objective },
              { label: "Description",      value: workItem.description },
              { label: "Expected Outcome", value: workItem.expected_outcome },
            ].map(({ label, value }) => (
              <GlassCard key={label} padding={false}>
                <div className="bg-white/5 px-5 py-3 border-b border-white/8">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-white/35">{label}</p>
                </div>
                <div className="px-5 py-4">
                  <p className="text-sm whitespace-pre-wrap text-white/80">{value}</p>
                </div>
              </GlassCard>
            ))}
          </div>

          {/* Right: Workers, policy, execution */}
          <div className="space-y-4">
            {/* Workers */}
            <GlassCard padding={false}>
              <div className="bg-white/5 px-5 py-3 border-b border-white/8">
                <p className="text-[10px] font-bold uppercase tracking-widest text-white/35">Workers</p>
              </div>
              <div className="px-5 py-4 space-y-2">
                {workItem.workers.length === 0 ? (
                  <p className="text-sm text-white/35">No workers assigned.</p>
                ) : (
                  workItem.workers.map((w, i) => (
                    <div key={i} className="flex items-center gap-2.5 rounded-lg bg-white/5 px-3 py-2">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ${
                        w.type === "ai_agent"
                          ? "bg-[#00DCC8]/15 text-[#00DCC8]"
                          : "bg-[#FF7AC8]/15 text-[#FF7AC8]"
                      }`}>
                        {w.type === "ai_agent" ? "AI" : "Human"}
                      </span>
                      <div>
                        <span className="text-sm font-medium text-white/85">
                          {w.type === "ai_agent" ? (w.agent_name ?? "Agent") : (w.user_name ?? w.user_email ?? "User")}
                        </span>
                        {w.type === "ai_agent" && w.agent_version && (
                          <span className="ml-1.5 font-mono text-xs text-white/35">v{w.agent_version}</span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </GlassCard>

            {/* Policy */}
            <GlassCard padding={false}>
              <div className="bg-white/5 px-5 py-3 border-b border-white/8">
                <p className="text-[10px] font-bold uppercase tracking-widest text-white/35">Policy</p>
              </div>
              <div className="px-5 py-4">
                {publishedPolicy ? (
                  <Link
                    href={`/policies/${publishedPolicy.id}?projectId=${projectId}&wiId=${wiId}`}
                    className="block space-y-2 hover:opacity-80 transition-opacity"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">v{publishedPolicy.version}</span>
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold bg-[#22C55E]/15 text-[#22C55E]">
                        published
                      </span>
                    </div>
                    <p className="text-xs text-white/45">
                      {publishedPolicy.stages.length} stage{publishedPolicy.stages.length !== 1 ? "s" : ""}
                      {publishedPolicy.checkpoints.length > 0 && ` · ${publishedPolicy.checkpoints.length} checkpoint${publishedPolicy.checkpoints.length !== 1 ? "s" : ""}`}
                      {" →"}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {publishedPolicy.stages.map((s) => (
                        <span
                          key={s.id}
                          className="inline-flex items-center rounded bg-white/8 px-2 py-0.5 text-xs text-white/55"
                        >
                          {s.sequence}. {s.name}
                        </span>
                      ))}
                    </div>
                  </Link>
                ) : draftPolicy ? (
                  <Link
                    href={`/policies/${draftPolicy.id}?projectId=${projectId}&wiId=${wiId}`}
                    className="block space-y-1 hover:opacity-80 transition-opacity"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">v{draftPolicy.version}</span>
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold bg-[#F59E0B]/15 text-[#F59E0B]">
                        draft
                      </span>
                    </div>
                    <p className="text-xs text-white/45">
                      {draftPolicy.stages.length} stage{draftPolicy.stages.length !== 1 ? "s" : ""} · Open to publish →
                    </p>
                  </Link>
                ) : (
                  <p className="text-sm text-white/35">
                    No published policy.{hasAiWorker ? " Use Generate Policy to create one." : ""}
                  </p>
                )}
              </div>
            </GlassCard>

            {/* Execution */}
            {execution && (
              <GlassCard padding={false} glow={execution.blocking_checkpoint ? "pink" : "none"}>
                <div className="bg-white/5 px-5 py-3 border-b border-white/8">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-white/35">Latest Execution</p>
                </div>
                <Link
                  href={`/executions/${execution.id}`}
                  className="block px-5 py-4 space-y-3 hover:opacity-80 transition-opacity"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">#{execution.execution_number}</span>
                    <StatusPill status={execution.status} dot />
                    {!TERMINAL.has(execution.status) && (
                      <span className="text-xs text-[#00DCC8] animate-pulse">Live</span>
                    )}
                  </div>

                  {execution.current_stage_id && (
                    <p className="text-xs text-white/45">
                      Stage:{" "}
                      <span className="text-white/70 font-medium">
                        {currentStage ? `${currentStage.sequence} — ${currentStage.name}` : "…"}
                      </span>
                    </p>
                  )}

                  {execution.blocking_checkpoint && (
                    <div className="rounded-lg bg-[#FF7AC8]/10 border border-[#FF7AC8]/20 px-3 py-2.5">
                      <p className="text-xs font-semibold text-[#FF7AC8] mb-0.5">
                        Waiting for {execution.blocking_checkpoint.type.replace(/_/g, " ")}
                      </p>
                      <p className="text-xs text-white/65">{execution.blocking_checkpoint.instruction}</p>
                    </div>
                  )}

                  {execution.status === "failed" && execution.error && (
                    <p className="text-xs text-[#EF4444]">✗ {execution.error}</p>
                  )}

                  {execution.started_at && (
                    <p className="font-mono text-xs text-white/30">
                      {TERMINAL.has(execution.status) && execution.completed_at
                        ? `Completed ${timeAgo(execution.completed_at)}`
                        : `Started ${timeAgo(execution.started_at)}`}
                    </p>
                  )}

                  <p className="text-xs text-[#5B6CFF]">Open execution workspace →</p>
                </Link>
              </GlassCard>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
