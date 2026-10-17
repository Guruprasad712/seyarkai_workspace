"use client"

import { use, useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { motion } from "motion/react"
import { apiFetch, ApiError } from "@/lib/api"
import { getToken } from "@/lib/auth"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { StatusPill } from "@/components/status-pill"
import { FreshnessBadge } from "@/components/freshness-badge"
import { TabBar } from "@/components/tab-bar"
import { InlineLoader } from "@/components/loader"
import type {
  ArtifactOut,
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

// ─── Markdown renderer ────────────────────────────────────────────────────────
// Lightweight inline renderer — no dependencies. Handles ##/###, **bold**,
// `code`, bullet lists. Keeps conversation feeling natural.

function MarkdownText({ text, className }: { text: string; className?: string }) {
  const lines = text.split("\n")
  const elements: React.ReactNode[] = []

  function renderInline(line: string): React.ReactNode[] {
    const parts: React.ReactNode[] = []
    // Split on **bold**, *italic*, `code`
    const regex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g
    let last = 0
    let m: RegExpExecArray | null
    let key = 0
    while ((m = regex.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index))
      const token = m[0]
      if (token.startsWith("**")) {
        parts.push(<strong key={key++} className="font-semibold text-white">{token.slice(2, -2)}</strong>)
      } else if (token.startsWith("*")) {
        parts.push(<em key={key++} className="italic text-white/90">{token.slice(1, -1)}</em>)
      } else {
        parts.push(<code key={key++} className="font-mono text-xs bg-white/10 rounded px-1 py-0.5 text-[#00DCC8]">{token.slice(1, -1)}</code>)
      }
      last = m.index + token.length
    }
    if (last < line.length) parts.push(line.slice(last))
    return parts
  }

  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (trimmed.startsWith("### ")) {
      elements.push(<p key={i} className="text-sm font-bold text-white mt-2 mb-0.5">{trimmed.slice(4)}</p>)
    } else if (trimmed.startsWith("## ")) {
      elements.push(<p key={i} className="text-base font-bold text-white mt-3 mb-1">{trimmed.slice(3)}</p>)
    } else if (trimmed.startsWith("# ")) {
      elements.push(<p key={i} className="text-lg font-bold text-white mt-3 mb-1">{trimmed.slice(2)}</p>)
    } else if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      elements.push(
        <div key={i} className="flex gap-2 my-0.5">
          <span className="text-white/40 mt-0.5 shrink-0">•</span>
          <span>{renderInline(trimmed.slice(2))}</span>
        </div>
      )
    } else if (trimmed === "") {
      if (i > 0 && lines[i - 1].trim() !== "") {
        elements.push(<div key={i} className="h-2" />)
      }
    } else {
      elements.push(<p key={i} className="leading-relaxed">{renderInline(line)}</p>)
    }
    i++
  }

  return <div className={`text-sm text-white/85 space-y-0.5 ${className ?? ""}`}>{elements}</div>
}
const STATUS_POLL_MS = 3000
const EVENT_POLL_MS = 2000

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function describeEvent(ev: EventOut): string {
  const p = ev.payload
  switch (ev.event_type) {
    case "execution.started":      return `Execution #${p.execution_number} started`
    case "stage.started":          return `Stage ${p.sequence} — ${p.name}`
    case "tool.called":            return `Tool called: ${p.tool_name}`
    case "tool.result": {
      const summary = String(p.summary ?? "")
      return `Tool result: ${summary.length > 100 ? summary.slice(0, 100) + "…" : summary}`
    }
    case "agent.message": {
      const preview = String(p.preview ?? "")
      return preview.length > 120 ? preview.slice(0, 120) + "…" : preview
    }
    case "stage.completed":        return `Stage ${p.sequence} completed`
    case "checkpoint.triggered":   return `Checkpoint reached — ${p.type}`
    case "execution.paused":       return "Execution paused"
    case "checkpoint.resolved":    return `Checkpoint ${p.decision}`
    case "execution.resumed":      return "Execution resumed"
    case "execution.completed":    return "Execution completed"
    case "agent.summary": {
      const s = String(p.summary ?? "")
      return `Summary: ${s.length > 120 ? s.slice(0, 120) + "…" : s}`
    }
    case "execution.failed":       return `Failed: ${p.error}`
    case "human.message": {
      const preview = String(p.preview ?? "")
      return `Guidance: ${preview.length > 120 ? preview.slice(0, 120) + "…" : preview}`
    }
    case "artifact.created":       return `Document created: ${String(p.name ?? "")}`
    case "executor.response": {
      const preview = String(p.preview ?? "")
      return `Answer: ${preview.length > 120 ? preview.slice(0, 120) + "…" : preview}`
    }
    default:                       return ev.event_type
  }
}

// ─── Checkpoint Actions ───────────────────────────────────────────────────────

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
    <div className="mt-4 space-y-3">
      {type === "input" ? (
        <>
          <textarea
            className="w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 resize-none focus:outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 transition-all"
            rows={3}
            placeholder="Enter your input…"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            disabled={submitting}
          />
          <BigButton
            variant="gradient"
            size="md"
            className="w-full"
            loading={submitting}
            disabled={!inputText.trim()}
            onClick={() => respond("input_provided", undefined, inputText.trim())}
          >
            Submit
          </BigButton>
        </>
      ) : type === "final_review" ? (
        <div className="flex gap-2">
          <BigButton variant="gradient" size="sm" loading={submitting} onClick={() => respond("approve")}>
            Complete ✓
          </BigButton>
          <BigButton variant="ghost" size="sm" disabled={submitting} onClick={() => respond("reject")}>
            Rework
          </BigButton>
        </div>
      ) : type === "review" ? (
        <div className="flex gap-2">
          <BigButton variant="gradient" size="sm" loading={submitting} onClick={() => respond("approve")}>
            Accept
          </BigButton>
          <BigButton variant="ghost" size="sm" disabled={submitting} onClick={() => respond("reject")}>
            Request Changes
          </BigButton>
        </div>
      ) : (
        <div className="flex gap-2">
          <BigButton variant="gradient" size="sm" loading={submitting} onClick={() => respond("approve")}>
            Approve
          </BigButton>
          <BigButton variant="danger" size="sm" disabled={submitting} onClick={() => respond("reject")}>
            Reject
          </BigButton>
        </div>
      )}
      {error && (
        <p className="text-xs text-[#EF4444] bg-[#EF4444]/10 px-3 py-2 rounded-lg border border-[#EF4444]/25">{error}</p>
      )}
    </div>
  )
}

// ─── Knowledge Event Row ──────────────────────────────────────────────────────

type KnowledgeDoc = { id: string; title: string; age_days: number; freshness: string }

function KnowledgeEventRow({ ev, isNew }: { ev: EventOut; isNew: boolean }) {
  const [open, setOpen] = useState(false)
  const p = ev.payload
  const docs = (p.documents ?? []) as KnowledgeDoc[]
  const staleCount = Number(p.stale_count ?? 0)
  const label = staleCount
    ? `Knowledge: ${docs.length} doc(s) retrieved (${staleCount} stale)`
    : `Knowledge: ${docs.length} doc(s) retrieved`

  return (
    <motion.div
      className="py-1.5"
      initial={isNew ? { opacity: 0, y: 6 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      <div className="flex items-start gap-2">
        <span className="font-mono text-xs text-white/35 shrink-0 mt-0.5 w-22">
          {fmtTime(ev.created_at)}
        </span>
        <span className="shrink-0 inline-flex items-center rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide bg-[#00DCC8]/15 text-[#00DCC8]">sys</span>
        <button
          className="text-xs text-white/75 leading-relaxed text-left hover:text-white transition-colors"
          onClick={() => setOpen((v) => !v)}
        >
          {label} {docs.length > 0 ? (open ? "▲" : "▼") : ""}
        </button>
      </div>
      {open && docs.length > 0 && (
        <div className="ml-[88px] mt-1.5 space-y-1">
          {docs.map((d) => (
            <div key={d.id} className="flex items-center gap-2">
              <span className="text-xs text-white/65">{d.title}</span>
              <FreshnessBadge freshness={d.freshness} age_days={d.age_days} />
            </div>
          ))}
        </div>
      )}
    </motion.div>
  )
}

// ─── Artifacts Tab ────────────────────────────────────────────────────────────

const _ARTIFACTS_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function ArtifactsTab({ artifacts }: { artifacts: ArtifactOut[] }) {
  const [htmlModal, setHtmlModal] = useState<{ id: string; html: string } | null>(null)
  const [htmlError, setHtmlError] = useState<{ id: string; msg: string } | null>(null)
  const [htmlLoading, setHtmlLoading] = useState<string | null>(null)

  async function openHtmlDoc(artifactId: string, artifactUrl: string) {
    setHtmlLoading(artifactId)
    setHtmlError(null)
    try {
      const token = getToken()
      const r = await fetch(`${_ARTIFACTS_API_BASE}${artifactUrl}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!r.ok) {
        throw new Error(r.status === 404 ? "Document not found" : `Failed to load (${r.status})`)
      }
      const html = await r.text()
      setHtmlModal({ id: artifactId, html })
    } catch (e) {
      setHtmlError({ id: artifactId, msg: (e as Error).message })
    } finally {
      setHtmlLoading(null)
    }
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-white/45">
        <svg className="h-10 w-10 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        <p className="text-sm font-medium">No documents generated yet</p>
      </div>
    )
  }
  return (
    <>
      {/* HTML document modal */}
      {htmlModal && (
        <div className="fixed inset-0 z-50 flex flex-col bg-black/80 backdrop-blur-sm">
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-[#0A0F1E]">
            <span className="text-sm font-semibold text-white">Document Preview</span>
            <button
              onClick={() => setHtmlModal(null)}
              className="rounded-full p-1.5 hover:bg-white/10 text-white/60 hover:text-white transition-colors"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <iframe
            srcDoc={htmlModal.html}
            sandbox=""
            className="flex-1 w-full border-0 bg-white"
            title="Document"
          />
        </div>
      )}

      <div className="flex flex-col h-full">
        <p className="shrink-0 px-5 pt-3 pb-1 text-xs text-white/35">What the team made. Summary first.</p>
        <div className="flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
            {artifacts.map((a) => (
              <GlassCard key={a.id} className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-3">
                  <span className="text-sm font-semibold text-white leading-snug flex-1">{a.name}</span>
                  <span className={`shrink-0 inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${
                    a.type === "google_doc"
                      ? "bg-[#00DCC8]/15 text-[#00DCC8]"
                      : "bg-[#F59E0B]/15 text-[#F59E0B]"
                  }`}>
                    {a.type === "google_doc" ? "Google Doc" : "HTML"}
                  </span>
                </div>
                <p className="font-mono text-xs text-white/40">
                  {new Date(a.created_at).toLocaleString()}
                </p>
                {a.type === "google_doc" ? (
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-auto"
                  >
                    <BigButton variant="primary" size="sm" className="w-full">
                      Open document ↗
                    </BigButton>
                  </a>
                ) : (
                  <div className="mt-auto flex flex-col gap-1.5">
                    <button
                      onClick={() => openHtmlDoc(a.id, a.url)}
                      disabled={htmlLoading === a.id}
                      className="w-full"
                    >
                      <BigButton variant="primary" size="sm" className="w-full" disabled={htmlLoading === a.id}>
                        {htmlLoading === a.id ? "Loading…" : "Open document"}
                      </BigButton>
                    </button>
                    {htmlError?.id === a.id && (
                      <p className="text-xs text-red-400">{htmlError.msg}</p>
                    )}
                  </div>
                )}
              </GlassCard>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

// ─── Summary Helpers ──────────────────────────────────────────────────────────

function DecisionBadge({ decision }: { decision: string }) {
  const approved = decision === "approve"
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide ${
      approved ? "bg-[#22C55E]/15 text-[#22C55E]" : "bg-[#EF4444]/15 text-[#EF4444]"
    }`}>
      {approved ? "Approved" : "Rejected"}
    </span>
  )
}

function StageSummaryCard({ stage }: { stage: StageSummary }) {
  return (
    <GlassCard padding={false} className="overflow-hidden">
      <div className="flex items-center gap-3 bg-white/5 px-5 py-3 border-b border-white/8">
        <span className="text-xs font-bold text-white/40 uppercase tracking-widest">Stage {stage.sequence}</span>
        <span className="text-sm font-semibold text-white">{stage.name}</span>
        {stage.checkpoint_decision && (
          <span className="ml-auto"><DecisionBadge decision={stage.checkpoint_decision} /></span>
        )}
      </div>
      <div className="divide-y divide-white/6">
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-white/40">Task Description</p>
          <p className="text-sm whitespace-pre-wrap text-white/85">{stage.description}</p>
        </div>
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-white/40">Expected Output</p>
          <p className="text-sm whitespace-pre-wrap text-white/55">{stage.expected_output}</p>
        </div>
        <div className="px-5 py-4">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-white/40">Agent Output</p>
          {stage.agent_output ? (
            <p className="text-sm whitespace-pre-wrap text-white/85">{stage.agent_output}</p>
          ) : (
            <p className="text-sm italic text-white/35">No output recorded.</p>
          )}
        </div>
        {stage.checkpoint_type && (
          <div className="px-5 py-4 bg-white/3">
            <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-white/40">
              Checkpoint — {stage.checkpoint_type.replace(/_/g, " ")}
            </p>
            {stage.checkpoint_decision ? (
              <div className="space-y-1">
                <DecisionBadge decision={stage.checkpoint_decision} />
                {stage.checkpoint_comment && (
                  <p className="text-sm text-white/75 mt-2 whitespace-pre-wrap">{stage.checkpoint_comment}</p>
                )}
              </div>
            ) : (
              <p className="text-sm italic text-white/35">No response recorded.</p>
            )}
          </div>
        )}
      </div>
    </GlassCard>
  )
}

function SummaryTab({ summary, status }: { summary: ExecutionSummaryOut; status: string }) {
  const fmt = (iso: string | null) => iso ? new Date(iso).toLocaleString() : "—"
  const duration = summary.started_at && summary.completed_at
    ? Math.round((new Date(summary.completed_at).getTime() - new Date(summary.started_at).getTime()) / 1000)
    : null

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-8 space-y-6">
        {/* Overview */}
        <GlassCard padding={false}>
          <div className="bg-white/5 px-5 py-3 border-b border-white/8">
            <p className="text-xs font-bold uppercase tracking-widest text-white/40">Execution Overview</p>
          </div>
          <div className="divide-y divide-white/6">
            <div className="px-5 py-4 grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-white/40 mb-1.5">Status</p>
                <StatusPill status={status} />
              </div>
              <div>
                <p className="text-xs text-white/40 mb-1.5">Started</p>
                <p className="text-sm text-white/75">{fmt(summary.started_at)}</p>
              </div>
              <div>
                <p className="text-xs text-white/40 mb-1.5">Completed</p>
                <p className="text-sm text-white/75">{fmt(summary.completed_at)}</p>
              </div>
              <div>
                <p className="text-xs text-white/40 mb-1.5">Duration</p>
                <p className="font-mono text-sm text-white/75">{duration !== null ? `${duration}s` : "—"}</p>
              </div>
            </div>
            {summary.error && (
              <div className="px-5 py-4 bg-[#EF4444]/5">
                <p className="text-xs font-bold uppercase tracking-widest text-[#EF4444] mb-1">Error</p>
                <p className="text-sm text-[#EF4444]/90">{summary.error}</p>
              </div>
            )}
          </div>
        </GlassCard>

        {/* Work item */}
        <GlassCard padding={false}>
          <div className="bg-white/5 px-5 py-3 border-b border-white/8">
            <p className="text-xs font-bold uppercase tracking-widest text-white/40">Work Item</p>
          </div>
          <div className="divide-y divide-white/6">
            {[
              { label: "Objective",        value: summary.work_item_objective },
              { label: "Description",      value: summary.work_item_description },
              { label: "Expected Outcome", value: summary.work_item_expected_outcome },
            ].map(({ label, value }) => (
              <div key={label} className="px-5 py-4">
                <p className="mb-1.5 text-xs font-bold uppercase tracking-widest text-white/40">{label}</p>
                <p className="text-sm whitespace-pre-wrap text-white/85">{value}</p>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Stages */}
        <div>
          <p className="mb-3 text-xs font-bold uppercase tracking-widest text-white/40">
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
          <GlassCard padding={false}>
            <div className="bg-white/5 px-5 py-3 border-b border-white/8 flex items-center gap-3">
              <p className="text-xs font-bold uppercase tracking-widest text-white/40">Final Review</p>
              {summary.final_review_decision && <DecisionBadge decision={summary.final_review_decision} />}
            </div>
            {summary.final_review_comment && (
              <div className="px-5 py-4">
                <p className="text-sm whitespace-pre-wrap text-white/85">{summary.final_review_comment}</p>
              </div>
            )}
          </GlassCard>
        )}
      </div>
    </div>
  )
}

// ─── Conversation Tab ─────────────────────────────────────────────────────────

function ConversationTab({
  events,
  executionId,
  cp,
  isAssignee,
  isTerminal,
  canGuide,
  onGoToCheckpoints,
  prevLength,
}: {
  events: EventOut[]
  executionId: string
  cp: CheckpointBrief | null
  isAssignee: boolean
  isTerminal: boolean
  canGuide: boolean
  onGoToCheckpoints: () => void
  prevLength: number
}) {
  const [composerMode, setComposerMode] = useState<"guide" | "ask">("guide")
  const [text, setText] = useState("")
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [askResponse, setAskResponse] = useState<string | null>(null)
  const [error, setError] = useState("")
  const bottomRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const atBottom = useRef(true)

  // Extract conversation-relevant events
  const convoEvents = events.filter((ev) =>
    ["agent.message", "stage_output", "human.message", "executor.response", "agent.summary"].includes(ev.event_type)
  )

  function handleScroll() {
    const el = listRef.current
    if (!el) return
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 50
  }

  useEffect(() => {
    if (atBottom.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [convoEvents.length])

  async function handleSend() {
    if (!text.trim()) return
    setError("")
    setSending(true)
    setAskResponse(null)
    try {
      if (composerMode === "guide") {
        await apiFetch(`/executions/${executionId}/messages`, {
          method: "POST",
          body: JSON.stringify({ content: text.trim() }),
        })
        setText("")
        setSent(true)
        setTimeout(() => setSent(false), 3000)
      } else {
        const res = await apiFetch<{ answer: string }>(`/executions/${executionId}/ask`, {
          method: "POST",
          body: JSON.stringify({ question: text.trim() }),
        })
        setAskResponse(res.answer)
        setText("")
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send")
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <p className="shrink-0 px-5 pt-3 pb-1 text-xs text-white/35">Talk to the agent like a teammate. It pings you when it&apos;s stuck.</p>
      {/* Messages */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-5 space-y-4"
      >
        {convoEvents.length === 0 && (
          <p className="text-sm text-white/35 text-center py-8">No messages yet — the agent will appear here.</p>
        )}
        {convoEvents.map((ev, i) => {
          const isNewItem = i >= prevLength
          const isHuman = ev.event_type === "human.message"
          const isSummary = ev.event_type === "agent.summary"
          const isAnswer = ev.event_type === "executor.response"
          const text = String(ev.payload?.preview ?? ev.payload?.summary ?? "")

          return (
            <motion.div
              key={ev.id}
              initial={isNewItem ? { opacity: 0, y: 8 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className={`flex ${isHuman ? "justify-end" : "justify-start"}`}
            >
              {isSummary ? (
                <div className="max-w-[85%] w-full rounded-xl bg-white/5 border border-white/10 px-4 py-3 space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[#C45BFF]">Summary so far</p>
                  <MarkdownText text={text} className="text-white/80" />
                </div>
              ) : isHuman ? (
                <div className="max-w-[75%] rounded-2xl rounded-tr-md bg-gradient-to-br from-[#5B6CFF] to-[#C45BFF] px-4 py-3">
                  <p className="text-sm text-white">{text}</p>
                </div>
              ) : isAnswer ? (
                <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-[#00DCC8]/15 border border-[#00DCC8]/25 px-4 py-3 space-y-2">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-[#00DCC8]">Answer</p>
                  <MarkdownText text={text} />
                </div>
              ) : (
                <div className="flex gap-3 max-w-[85%]">
                  <div className="shrink-0 h-7 w-7 rounded-lg bg-gradient-to-br from-[#5B6CFF] to-[#C45BFF] flex items-center justify-center mt-0.5">
                    <span className="text-white text-[10px] font-bold">AI</span>
                  </div>
                  <div className="rounded-2xl rounded-tl-md bg-white/8 border border-white/10 px-4 py-3">
                    <MarkdownText text={text} />
                  </div>
                </div>
              )}
            </motion.div>
          )
        })}

        {/* Checkpoint nudge */}
        {cp && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl rounded-tl-md bg-[#FF7AC8]/12 border border-[#FF7AC8]/25 px-4 py-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-[#FF7AC8] animate-pulse" />
                <p className="text-sm font-semibold text-[#FF7AC8]">I&apos;ve stopped. I need a human.</p>
              </div>
              <p className="text-xs text-white/60">{cp.instruction}</p>
              <BigButton variant="ghost" size="sm" onClick={onGoToCheckpoints}>
                Go to Checkpoint →
              </BigButton>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      {!isTerminal && canGuide && (
        <div className="shrink-0 border-t border-white/8 px-4 py-4 bg-[rgba(7,10,20,0.7)] backdrop-blur-md space-y-3">
          {/* Mode toggle */}
          <div className="flex items-center gap-1 w-fit rounded-xl bg-white/6 p-1">
            {(["guide", "ask"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setComposerMode(mode)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  composerMode === mode
                    ? "bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF] text-white"
                    : "text-white/50 hover:text-white"
                }`}
              >
                {mode === "guide" ? "Guide" : "Ask"}
              </button>
            ))}
          </div>
          <p className="text-xs text-white/40">
            {composerMode === "guide"
              ? "Leave a note for the agent — injected before the next stage."
              : "Ask a question about this execution."}
          </p>
          <div className="flex gap-2">
            <textarea
              className="flex-1 rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 resize-none focus:outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 transition-all"
              rows={2}
              placeholder={composerMode === "guide" ? "e.g. Focus on the error handling path…" : "e.g. What did the agent find?"}
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={sending}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend() }}
            />
            <BigButton
              variant="gradient"
              size="md"
              loading={sending}
              disabled={!text.trim()}
              onClick={handleSend}
              className="shrink-0 self-end"
            >
              Send
            </BigButton>
          </div>
          {error && <p className="text-xs text-[#EF4444]">{error}</p>}
          {sent && <p className="text-xs text-[#22C55E]">Guidance sent ✓</p>}
          {askResponse && (
            <div className="rounded-xl bg-[#00DCC8]/10 border border-[#00DCC8]/20 px-4 py-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-[#00DCC8] mb-1">Answer</p>
              <p className="text-sm text-white/85 whitespace-pre-wrap">{askResponse}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Timeline Tab ─────────────────────────────────────────────────────────────

const nodeColor: Record<string, string> = {
  system: "#00DCC8",
  agent: "#C45BFF",
  human: "#FF7AC8",
}

function TimelineTab({
  events,
  isTerminal,
  prevLength,
  timelineRef,
}: {
  events: EventOut[]
  isTerminal: boolean
  prevLength: number
  timelineRef: React.RefObject<HTMLDivElement | null>
}) {
  const [filter, setFilter] = useState<"all" | "agent" | "tool" | "human">("all")

  const filtered = filter === "all" ? events
    : filter === "tool" ? events.filter((e) => e.event_type.startsWith("tool."))
    : filter === "agent" ? events.filter((e) => e.actor_type === "agent")
    : events.filter((e) => e.actor_type === "human")

  return (
    <div className="flex flex-col h-full">
      <p className="shrink-0 px-5 pt-3 pb-1 text-xs text-white/35">Every move, in order. Reasoning summarised, never raw.</p>
      {/* Filter bar */}
      <div className="shrink-0 px-4 py-3 border-b border-white/8 flex items-center gap-2 flex-wrap">
        <span className="text-xs text-white/40 mr-1">Filter:</span>
        {(["all", "agent", "tool", "human"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
              filter === f
                ? "bg-white/15 text-white"
                : "text-white/40 hover:text-white hover:bg-white/8"
            }`}
          >
            {f === "all" ? "All" : f === "agent" ? "Reasoning" : f === "tool" ? "Tool calls" : "Human"}
          </button>
        ))}
        <span className="ml-auto text-xs text-white/25 italic">Reasoning is summarised, never raw</span>
      </div>

      <div ref={timelineRef} className="flex-1 overflow-y-auto px-4 py-4">
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-[18px] top-3 bottom-3 w-px bg-white/10" />

          <div className="space-y-0.5">
            {filtered.length === 0 && (
              <p className="text-xs text-white/35 pl-10">No events.</p>
            )}
            {filtered.map((ev, i) => {
              const isNew = events.indexOf(ev) >= prevLength
              const color = nodeColor[ev.actor_type] ?? "#ffffff"

              if (ev.event_type === "knowledge.retrieved") {
                return <KnowledgeEventRow key={ev.id} ev={ev} isNew={isNew} />
              }

              return (
                <motion.div
                  key={ev.id}
                  className="flex items-start gap-3 py-1.5"
                  initial={isNew ? { opacity: 0, x: -6 } : false}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                >
                  {/* Node */}
                  <div className="relative z-10 shrink-0 mt-0.5">
                    <div
                      className="h-4 w-4 rounded-full border-2 bg-[#070A14]"
                      style={{ borderColor: color }}
                    />
                  </div>
                  {/* Content */}
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <span className="font-mono text-xs text-white/30 shrink-0 mt-0.5 w-20 tabular-nums">
                      {fmtTime(ev.created_at)}
                    </span>
                    <span
                      className="shrink-0 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                      style={{ background: `${color}18`, color }}
                    >
                      {ev.actor_type}
                    </span>
                    <span className="text-xs text-white/70 leading-relaxed min-w-0 break-words">
                      {describeEvent(ev)}
                    </span>
                  </div>
                </motion.div>
              )
            })}
          </div>

          {!isTerminal && (
            <div className="flex items-center gap-2 pl-7 py-2 text-xs text-white/35">
              <span className="h-1.5 w-1.5 rounded-full bg-[#00DCC8] animate-pulse" />
              Waiting for updates…
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Checkpoints Tab ──────────────────────────────────────────────────────────

function CheckpointsTab({
  cp,
  execution,
  isAssignee,
  executionId,
  policy,
  onResponse,
  userDirectory,
}: {
  cp: CheckpointBrief | null
  execution: ExecutionOut
  isAssignee: boolean
  executionId: string
  policy: PolicyOut | null
  onResponse: (nextAction: string, newStatus: string) => void
  userDirectory: Map<string, { name: string; role: string }>
}) {
  return (
    <div className="flex flex-col h-full">
      <p className="shrink-0 px-5 pt-3 pb-1 text-xs text-white/35">The agent stops here. Nothing moves until a human says yes.</p>
      <div className="flex-1 overflow-y-auto p-5">
      <div className="max-w-2xl mx-auto space-y-5">
        {cp ? (
          <GlassCard glow="pink" padding={false} className="overflow-hidden">
            <div className="bg-[#FF7AC8]/10 px-5 py-3 border-b border-[#FF7AC8]/20 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-[#FF7AC8] animate-pulse" />
              <p className="text-xs font-bold uppercase tracking-widest text-[#FF7AC8]">
                Waiting for your review
              </p>
            </div>
            <div className="px-5 py-5 space-y-5">
              <div>
                <p className="text-sm font-semibold text-white/90 leading-snug">{cp.instruction}</p>
                <p className="text-xs text-white/45 mt-1 capitalize">{cp.type.replace(/_/g, " ")} checkpoint</p>
              </div>

              {/* Agent summary */}
              <div className="rounded-xl bg-white/5 border border-white/8 px-4 py-4 space-y-2">
                <p className="text-xs font-bold uppercase tracking-widest text-white/35">Agent Summary</p>
                {execution.pending_summary ? (
                  <MarkdownText text={execution.pending_summary} className="text-sm text-white/80" />
                ) : (
                  <p className="text-sm italic text-white/35">Summary pending…</p>
                )}
              </div>

              {/* Assigned to */}
              {(() => {
                const assignee = userDirectory.get(cp.assigned_user_id)
                return (
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs text-white/40">Assigned to:</p>
                    {assignee ? (
                      <>
                        <p className="text-xs text-white/80 font-medium">{assignee.name}</p>
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-white/10 text-white/50 border border-white/15">
                          {assignee.role}
                        </span>
                      </>
                    ) : (
                      <p className="font-mono text-xs text-white/70">{cp.assigned_user_id}</p>
                    )}
                  </div>
                )
              })()}

              {isAssignee ? (
                <CheckpointActions
                  executionId={executionId}
                  checkpoint={cp}
                  onResponse={onResponse}
                />
              ) : (
                <p className="text-xs text-white/40 bg-white/5 px-3 py-2 rounded-lg">
                  You are not the assigned reviewer for this checkpoint.
                </p>
              )}
            </div>
          </GlassCard>
        ) : TERMINAL.has(execution.status) ? (
          <div className="text-center py-12 text-white/40">
            <p className="text-sm">Execution finished — no pending checkpoints.</p>
          </div>
        ) : (
          <div className="text-center py-12 text-white/40">
            <p className="text-sm">No checkpoint pending.</p>
            <p className="text-xs mt-1">Checkpoints will appear here when the agent needs your review.</p>
          </div>
        )}

        {/* All checkpoints list from policy */}
        {policy && policy.checkpoints.length > 0 && (
          <GlassCard padding={false}>
            <div className="px-5 py-3 border-b border-white/8">
              <p className="text-xs font-bold uppercase tracking-widest text-white/35">All Checkpoints</p>
            </div>
            <div className="divide-y divide-white/6">
              {policy.checkpoints.map((chk) => {
                const stage = policy.stages.find((s) => s.id === chk.stage_id)
                const isCurrent = cp?.id === chk.id
                return (
                  <div key={chk.id} className="flex items-center gap-3 px-5 py-3">
                    <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                      isCurrent ? "bg-[#FF7AC8] animate-pulse" : "bg-white/20"
                    }`} />
                    <div>
                      <p className="text-xs font-medium text-white/70">
                        {stage ? `Stage ${stage.sequence} — ${stage.name}` : chk.instruction}
                      </p>
                      <p className="text-[11px] text-white/35 capitalize">{chk.type.replace(/_/g, " ")}</p>
                    </div>
                    {isCurrent && (
                      <span className="ml-auto text-[10px] font-bold uppercase tracking-widest text-[#FF7AC8]">Active</span>
                    )}
                  </div>
                )
              })}
            </div>
          </GlassCard>
        )}
      </div>
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

  const [execution, setExecution]         = useState<ExecutionOut | null>(null)
  const [workItem, setWorkItem]           = useState<WorkItem | null>(null)
  const [policy, setPolicy]               = useState<PolicyOut | null>(null)
  const [events, setEvents]               = useState<EventOut[]>([])
  const [loading, setLoading]             = useState(true)
  const [error, setError]                 = useState("")
  const [activeTab, setActiveTab]         = useState<"conversation" | "timeline" | "artifacts" | "checkpoints">("conversation")
  const [summary, setSummary]             = useState<ExecutionSummaryOut | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [userDirectory, setUserDirectory] = useState<Map<string, { name: string; role: string }>>(new Map())

  const lastEventIdRef  = useRef<string | null>(null)
  const timelineRef     = useRef<HTMLDivElement>(null)
  const statusPollRef   = useRef<ReturnType<typeof setInterval> | null>(null)
  const eventPollRef    = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevEventsLen   = useRef(0)

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
      prevEventsLen.current = initialEvents.length
      if (initialEvents.length > 0) {
        lastEventIdRef.current = initialEvents[initialEvents.length - 1].id
      }
      apiFetch<WorkItem>(`/work-items/${exec.work_item_id}`)
        .then(setWorkItem)
        .catch(() => {})
      apiFetch<{ id: string; name: string; role: string }[]>("/users/directory")
        .then((list) => setUserDirectory(new Map(list.map((u) => [u.id, { name: u.name, role: u.role }]))))
        .catch(() => {})
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load execution")
    } finally {
      setLoading(false)
    }
  }, [executionId])

  useEffect(() => { loadInitial() }, [loadInitial])

  // ── Load policy ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!execution?.policy_id || policy?.id === execution.policy_id) return
    apiFetch<PolicyOut>(`/policies/${execution.policy_id}`)
      .then(setPolicy)
      .catch(() => {})
  }, [execution?.policy_id, policy?.id])

  // ── Status polling ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!execution || TERMINAL.has(execution.status)) {
      if (statusPollRef.current) { clearInterval(statusPollRef.current); statusPollRef.current = null }
      return
    }
    statusPollRef.current = setInterval(async () => {
      try {
        const updated = await apiFetch<ExecutionOut>(`/executions/${executionId}`)
        setExecution(updated)
        if (TERMINAL.has(updated.status)) { clearInterval(statusPollRef.current!); statusPollRef.current = null }
      } catch { /* keep polling */ }
    }, STATUS_POLL_MS)
    return () => { if (statusPollRef.current) { clearInterval(statusPollRef.current); statusPollRef.current = null } }
  }, [execution?.id, execution?.status, executionId])

  // ── Event polling ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!execution || TERMINAL.has(execution.status)) {
      if (execution && TERMINAL.has(execution.status)) {
        const afterParam = lastEventIdRef.current ? `?after=${lastEventIdRef.current}&limit=100` : "?limit=100"
        apiFetch<EventOut[]>(`/executions/${executionId}/events${afterParam}`)
          .then((newEvs) => {
            if (newEvs.length > 0) {
              setEvents((prev) => { prevEventsLen.current = prev.length; return [...prev, ...newEvs] })
              lastEventIdRef.current = newEvs[newEvs.length - 1].id
            }
          })
          .catch(() => {})
      }
      if (eventPollRef.current) { clearInterval(eventPollRef.current); eventPollRef.current = null }
      return
    }
    eventPollRef.current = setInterval(async () => {
      const afterParam = lastEventIdRef.current ? `?after=${lastEventIdRef.current}&limit=100` : "?limit=100"
      try {
        const newEvs = await apiFetch<EventOut[]>(`/executions/${executionId}/events${afterParam}`)
        if (newEvs.length > 0) {
          setEvents((prev) => { prevEventsLen.current = prev.length; return [...prev, ...newEvs] })
          lastEventIdRef.current = newEvs[newEvs.length - 1].id
        }
      } catch { /* keep polling */ }
    }, EVENT_POLL_MS)
    return () => { if (eventPollRef.current) { clearInterval(eventPollRef.current); eventPollRef.current = null } }
  }, [execution?.id, execution?.status, executionId])

  // ── Auto-scroll timeline ──────────────────────────────────────────────────

  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTop = timelineRef.current.scrollHeight
    }
  }, [events])

  // ── Summary load ──────────────────────────────────────────────────────────

  async function loadSummary() {
    if (summaryLoading || summary) return
    setSummaryLoading(true)
    try {
      const s = await apiFetch<ExecutionSummaryOut>(`/executions/${executionId}/summary`)
      setSummary(s)
    } catch { /* best-effort */ } finally { setSummaryLoading(false) }
  }

  // ── Checkpoint response ───────────────────────────────────────────────────

  function handleCheckpointResponse(nextAction: string, newStatus: string) {
    setExecution((prev) => prev ? { ...prev, status: newStatus, blocking_checkpoint: null } : prev)
  }

  // ─────────────────────────────────────────────────────────────────────────

  if (loading) {
    return <InlineLoader label="Loading execution…" />
  }

  if (error || !execution) {
    return (
      <div className="px-6 py-10">
        <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
          {error || "Execution not found"}
        </div>
        <div className="mt-4">
          <Link href="/" className="text-sm text-white/50 hover:text-white transition-colors">← Dashboard</Link>
        </div>
      </div>
    )
  }

  const currentStage = policy?.stages.find((s) => s.id === execution.current_stage_id)
  const totalStages = policy?.stages.length ?? 0
  const cp = execution.blocking_checkpoint
  const isAssignee = cp !== null && (user?.id === cp.assigned_user_id || user?.role === "admin")
  const canGuide = can.sendGuidance(user?.role ?? "")
  const isTerminal = TERMINAL.has(execution.status)
  const backHref = workItem?.project_id
    ? `/projects/${workItem.project_id}/work-items/${execution.work_item_id}`
    : "/"

  const tabs = [
    { id: "conversation", label: "Conversation" },
    { id: "timeline",     label: "Timeline" },
    { id: "artifacts",    label: "Artifacts" },
    { id: "checkpoints",  label: "Checkpoints", dot: !!cp, dotColor: "#FF7AC8" },
    ...(isTerminal ? [{ id: "summary", label: "Summary" }] : []),
  ]

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#070A14]">

      {/* Top bar */}
      <div className="shrink-0 border-b border-white/8 bg-[rgba(7,10,20,0.9)] backdrop-blur-xl px-5 py-3">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div className="flex items-center gap-3 min-w-0">
            <Link href={backHref} className="text-sm text-white/45 hover:text-white transition-colors shrink-0">
              ← {workItem?.name ?? "Work Item"}
            </Link>
            <span className="text-white/20">/</span>
            <span className="font-heading font-semibold text-white text-sm">
              Execution #{execution.execution_number}
            </span>
            <StatusPill status={execution.status} dot />
            {!isTerminal && (
              <div className="flex items-center gap-1.5 text-xs text-[#00DCC8]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#00DCC8] animate-pulse" />
                Live
              </div>
            )}
          </div>

          <p className="text-xs text-white/35 mt-0.5">Live. Shared. Governed.</p>

          {/* Stage progress */}
          {currentStage && (
            <div className="shrink-0 text-right hidden sm:block">
              <p className="text-xs text-white/40">
                Stage {currentStage.sequence}{totalStages > 0 ? ` of ${totalStages}` : ""}
              </p>
              <p className="text-xs font-medium text-white/70 max-w-[180px] truncate">{currentStage.name}</p>
            </div>
          )}
        </div>

        {/* Tab bar */}
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={(id) => {
            setActiveTab(id as typeof activeTab)
            if (id === "summary") loadSummary()
          }}
        />
      </div>

      {/* Left + right 2-col for timeline/conversation; full-width for others */}
      {(activeTab === "timeline" || activeTab === "conversation") ? (
        <div className="flex flex-1 overflow-hidden">
          {/* LEFT sidebar — stage list */}
          <div className="hidden lg:flex flex-col w-[260px] shrink-0 border-r border-white/8 overflow-y-auto px-4 py-5 gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-white/30 mb-3">Stages</p>
              {policy?.stages ? (
                <div className="space-y-1">
                  {policy.stages.map((s) => {
                    const isActive = s.id === execution.current_stage_id
                    const hasCheckpoint = policy.checkpoints.some((c) => c.stage_id === s.id)
                    return (
                      <div
                        key={s.id}
                        className={`flex items-center gap-2.5 rounded-lg px-3 py-2 transition-colors ${
                          isActive ? "bg-[#00DCC8]/10 border border-[#00DCC8]/20" : "hover:bg-white/5"
                        }`}
                      >
                        <span className={`text-[11px] font-bold tabular-nums w-5 text-center shrink-0 ${
                          isActive ? "text-[#00DCC8]" : "text-white/30"
                        }`}>{s.sequence}</span>
                        <span className={`text-xs font-medium leading-snug ${isActive ? "text-white" : "text-white/55"}`}>
                          {s.name}
                        </span>
                        {hasCheckpoint && (
                          <span className="ml-auto h-2 w-2 rounded-sm bg-[#FF7AC8]/60 shrink-0 rotate-45" title="Has checkpoint" />
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : execution.status === "queued" ? (
                <p className="text-xs text-white/35">Waiting to start…</p>
              ) : (
                <p className="text-xs text-white/35">Loading stages…</p>
              )}
            </div>

            {/* Progress bar */}
            {totalStages > 0 && currentStage && (
              <div className="space-y-1.5">
                <p className="text-[10px] text-white/30">
                  {currentStage.sequence} / {totalStages} stages
                </p>
                <div className="h-1 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[#00DCC8] to-[#5B6CFF] transition-all"
                    style={{ width: `${(currentStage.sequence / totalStages) * 100}%` }}
                  />
                </div>
              </div>
            )}

            {execution.status === "failed" && execution.error && (
              <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/20 px-3 py-2.5">
                <p className="text-xs font-bold text-[#EF4444] mb-1">Error</p>
                <p className="text-xs text-[#EF4444]/80">{execution.error}</p>
              </div>
            )}

            {execution.started_at && (
              <div className="mt-auto pt-4 border-t border-white/8 space-y-0.5">
                <p className="font-mono text-[11px] text-white/30">
                  Started {new Date(execution.started_at).toLocaleString()}
                </p>
                {execution.completed_at && (
                  <p className="font-mono text-[11px] text-white/30">
                    Done {new Date(execution.completed_at).toLocaleString()}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Main content area */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {activeTab === "conversation" && (
              <ConversationTab
                events={events}
                executionId={executionId}
                cp={cp}
                isAssignee={isAssignee}
                isTerminal={isTerminal}
                canGuide={canGuide}
                onGoToCheckpoints={() => setActiveTab("checkpoints")}
                prevLength={prevEventsLen.current}
              />
            )}
            {activeTab === "timeline" && (
              <TimelineTab
                events={events}
                isTerminal={isTerminal}
                prevLength={prevEventsLen.current}
                timelineRef={timelineRef}
              />
            )}
          </div>
        </div>
      ) : activeTab === "artifacts" ? (
        <ArtifactsTab artifacts={execution.artifacts} />
      ) : activeTab === "checkpoints" ? (
        <CheckpointsTab
          cp={cp}
          execution={execution}
          isAssignee={isAssignee}
          executionId={executionId}
          policy={policy}
          onResponse={handleCheckpointResponse}
          userDirectory={userDirectory}
        />
      ) : activeTab === "summary" && isTerminal ? (
        summaryLoading ? (
          <InlineLoader label="Loading summary…" />
        ) : summary ? (
          <SummaryTab summary={summary} status={execution.status} />
        ) : (
          <div className="flex flex-1 items-center justify-center text-sm text-white/40">
            Summary unavailable.
          </div>
        )
      ) : null}
    </div>
  )
}
