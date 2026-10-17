"use client"

import { use, useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { ChevronDown, ChevronRight, Loader2, Plus, Trash2 } from "lucide-react"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { StatusPill } from "@/components/status-pill"
import { BigButton } from "@/components/big-button"
import { GlassCard } from "@/components/glass-card"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import type { Agent, AgentVersion, Capability, McpTool, PublishFailure } from "@/lib/types"

// ─── Helpers ────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

function Badge({ status }: { status: string }) {
  return <StatusPill status={status} />
}

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium">{label}</label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

// ─── Version edit / add form ─────────────────────────────────────────────────

type VersionFormProps = {
  agentId: string
  versionId?: string // present = edit, absent = add
  prefill?: AgentVersion
  allTools: McpTool[]
  onSaved: () => void
  onCancel: () => void
}

function VersionForm({
  agentId,
  versionId,
  prefill,
  allTools,
  onSaved,
  onCancel,
}: VersionFormProps) {
  const [instructions, setInstructions] = useState(prefill?.instructions ?? "")
  const [capabilities, setCapabilities] = useState<Capability[]>(
    prefill?.capabilities?.length ? prefill.capabilities : [{ name: "", description: "" }],
  )
  const [selectedTools, setSelectedTools] = useState<Set<string>>(
    new Set(prefill?.tool_ids ?? []),
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  const activeTools = allTools.filter((t) => t.status === "active")

  function toggleTool(id: string) {
    setSelectedTools((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function addCap() {
    setCapabilities((prev) => [...prev, { name: "", description: "" }])
  }
  function removeCap(i: number) {
    setCapabilities((prev) => prev.filter((_, idx) => idx !== i))
  }
  function updateCap(i: number, f: keyof Capability, v: string) {
    setCapabilities((prev) => prev.map((c, idx) => (idx === i ? { ...c, [f]: v } : c)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    const body = {
      instructions,
      capabilities: capabilities.filter((c) => c.name.trim()),
      tool_ids: Array.from(selectedTools),
    }
    try {
      if (versionId) {
        await apiFetch(`/agents/${agentId}/versions/${versionId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      } else {
        await apiFetch(`/agents/${agentId}/versions`, {
          method: "POST",
          body: JSON.stringify(body),
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-xl glass p-4">
      <Field label="Instructions">
        <textarea
          className={inputCls + " min-h-[100px] resize-y font-mono text-xs"}
          required
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </Field>

      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-sm font-medium text-white/80">Capabilities</label>
          <button
            type="button"
            onClick={addCap}
            className="flex items-center gap-1 text-xs text-[#5B6CFF] hover:text-[#C45BFF] transition-colors"
          >
            <Plus className="h-3 w-3" />
            Add
          </button>
        </div>
        <div className="space-y-2">
          {capabilities.map((cap, idx) => (
            <div key={idx} className="flex gap-2">
              <input
                placeholder="Name"
                className={inputCls + " flex-1"}
                required={idx === 0}
                value={cap.name}
                onChange={(e) => updateCap(idx, "name", e.target.value)}
              />
              <input
                placeholder="Description"
                className={inputCls + " flex-[2]"}
                value={cap.description}
                onChange={(e) => updateCap(idx, "description", e.target.value)}
              />
              {capabilities.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeCap(idx)}
                  className="p-1.5 rounded-lg text-white/30 hover:text-[#EF4444] hover:bg-[#EF4444]/10 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium">Tools</label>
        {activeTools.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active tools available.</p>
        ) : (
          <div className="space-y-2">
            {activeTools.map((tool) => (
              <label
                key={tool.id}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-border px-3 py-2.5 hover:bg-muted/40"
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={selectedTools.has(tool.id)}
                  onChange={() => toggleTool(tool.id)}
                />
                <div>
                  <p className="text-sm font-medium">{tool.name}</p>
                  <p className="text-xs text-muted-foreground">{tool.description}</p>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2">
        <BigButton type="submit" variant="gradient" size="md" loading={submitting} disabled={submitting}>
          {submitting ? "Saving…" : versionId ? "Save changes" : "Add version"}
        </BigButton>
        <BigButton type="button" variant="ghost" size="md" onClick={onCancel}>
          Cancel
        </BigButton>
      </div>
    </form>
  )
}

// ─── Version row ─────────────────────────────────────────────────────────────

type VersionRowProps = {
  version: AgentVersion
  agentId: string
  allTools: McpTool[]
  onRefresh: () => void
  canEdit: boolean
}

function VersionRow({ version, agentId, allTools, onRefresh, canEdit }: VersionRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [publishFailures, setPublishFailures] = useState<PublishFailure[]>([])

  const toolsById = Object.fromEntries(allTools.map((t) => [t.id, t]))
  const toolNames = version.tool_ids.map((id) => toolsById[id]?.name ?? id).join(", ")

  async function handlePublish() {
    setPublishFailures([])
    setPublishing(true)
    try {
      await apiFetch(`/agents/${agentId}/versions/${version.id}/publish`, {
        method: "POST",
      })
      onRefresh()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const failures = extractPublishFailures(err.body)
        if (failures) {
          setPublishFailures(failures)
          return
        }
      }
      setPublishFailures([{ code: "error", message: err instanceof ApiError ? err.message : "Publish failed" }])
    } finally {
      setPublishing(false)
    }
  }

  // Map failure codes to human-readable field labels
  const failureLabels: Record<string, string> = {
    not_draft: "Status",
    missing_instructions: "Instructions",
    no_capabilities: "Capabilities",
    no_tools: "Tools",
    inactive_tool: "Tools",
  }

  return (
    <div className="rounded-xl glass overflow-hidden">
      {/* Header row — entire row is clickable to expand */}
      <div
        className="flex items-center gap-3 px-4 py-4 flex-wrap cursor-pointer select-none hover:bg-white/5 active:bg-white/8 transition-colors duration-150"
        onClick={() => !editing && setExpanded((v) => !v)}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-white/40 shrink-0 transition-transform duration-200" />
        ) : (
          <ChevronRight className="h-4 w-4 text-white/40 shrink-0 transition-transform duration-200" />
        )}
        <span className="text-sm font-bold text-white">v{version.version}</span>
        <Badge status={version.status} />
        {version.published_at && (
          <span className="text-xs text-white/35 font-mono">
            {new Date(version.published_at).toLocaleDateString()}
          </span>
        )}
        {toolNames && (
          <span className="text-xs text-white/35">
            Tools: {toolNames}
          </span>
        )}
        <div className="ml-auto flex gap-2" onClick={(e) => e.stopPropagation()}>
          {version.status === "draft" && !editing && canEdit && (
            <>
              <BigButton type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit
              </BigButton>
              <BigButton type="button" variant="gradient" size="sm" disabled={publishing} loading={publishing} onClick={handlePublish}>
                {publishing ? "" : "Publish"}
              </BigButton>
            </>
          )}
        </div>
      </div>

      {/* Publish failures */}
      {publishFailures.length > 0 && (
        <div className="mx-4 mb-3 rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-3 py-2">
          <p className="mb-1 text-xs font-medium text-[#EF4444]">
            Publish validation failed
          </p>
          <ul className="space-y-0.5">
            {publishFailures.map((f) => (
              <li key={f.code} className="text-xs text-[#EF4444]">
                <span className="font-medium">{failureLabels[f.code] ?? f.code}:</span>{" "}
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Instructions expand */}
      {expanded && !editing && (
        <div className="border-t border-white/10 px-4 py-3">
          <p className="mb-1 text-xs font-medium text-white/40 uppercase tracking-widest">Instructions</p>
          <pre className="whitespace-pre-wrap font-mono text-xs text-white/70">
            {version.instructions}
          </pre>
          {version.capabilities.length > 0 && (
            <>
              <p className="mb-1 mt-3 text-xs font-medium text-white/40 uppercase tracking-widest">Capabilities</p>
              <ul className="space-y-1">
                {version.capabilities.map((c, i) => (
                  <li key={i} className="text-xs text-white/70">
                    <span className="font-medium text-white/90">{c.name}</span>
                    {c.description ? ` — ${c.description}` : ""}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Inline edit form */}
      {editing && (
        <div className="border-t border-white/10 p-4">
          <VersionForm
            agentId={agentId}
            versionId={version.id}
            prefill={version}
            allTools={allTools}
            onSaved={() => {
              setEditing(false)
              onRefresh()
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      )}
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const router = useRouter()
  const { user } = useAuth()
  const canEdit = can.editAgents(user?.role ?? "")

  const [agent, setAgent] = useState<Agent | null>(null)
  const [tools, setTools] = useState<McpTool[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [addingVersion, setAddingVersion] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [a, ts] = await Promise.all([
        apiFetch<Agent>(`/agents/${id}`),
        apiFetch<McpTool[]>("/mcp-tools"),
      ])
      setAgent(a)
      setTools(ts)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load agent")
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="min-h-screen bg-[#070A14]">
        <div className="mx-auto max-w-3xl px-4 py-10">
          <div className="flex items-center gap-2 text-sm text-white/40">
            <Loader2 className="h-4 w-4 animate-spin text-[#5B6CFF]" />
            Loading…
          </div>
        </div>
      </div>
    )
  }

  if (error || !agent) {
    return (
      <div className="min-h-screen bg-[#070A14]">
        <div className="mx-auto max-w-3xl px-4 py-10">
          <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
            {error || "Agent not found"}
          </div>
          <BigButton className="mt-4" variant="ghost" size="md" onClick={() => router.push("/agents")}>
            ← Back to agents
          </BigButton>
        </div>
      </div>
    )
  }

  const publishedVersion = agent.versions.find((v) => v.status === "published")
  const hasDraft = agent.versions.some((v) => v.status === "draft")

  return (
    <div className="min-h-screen bg-[#070A14]">
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Back */}
      <div className="mb-6">
        <Link
          href="/agents"
          className="text-sm text-white/45 hover:text-white transition-colors"
        >
          ← Agent Library
        </Link>
      </div>

      {/* Agent header */}
      <GlassCard className="mb-8" style={{ background: "rgba(0,220,200,0.05)" } as React.CSSProperties}>
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="font-heading text-3xl font-black text-white">{agent.name}</h1>
              <Badge status={agent.status} />
            </div>
            <p className="mt-0.5 font-mono text-xs text-[#00DCC8]/70">
              {agent.agent_code}
            </p>
          </div>
        </div>
        {agent.description && (
          <p className="mt-3 text-sm text-white/55">{agent.description}</p>
        )}
        {agent.role_purpose && (
          <p className="mt-1 text-sm text-white/70">
            <span className="text-white/35">Role:</span> {agent.role_purpose}
          </p>
        )}
      </GlassCard>

      {/* Versions */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-xl font-bold text-white">Versions</h2>
          {!hasDraft && canEdit && (
            <BigButton
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setAddingVersion(true)}
              disabled={addingVersion}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add version
            </BigButton>
          )}
        </div>

        {/* Add version form — pre-filled from published */}
        {addingVersion && (
          <VersionForm
            agentId={agent.id}
            prefill={publishedVersion}
            allTools={tools}
            onSaved={() => {
              setAddingVersion(false)
              load()
            }}
            onCancel={() => setAddingVersion(false)}
          />
        )}

        {agent.versions.length === 0 && !addingVersion && (
          <p className="text-sm text-muted-foreground">No versions yet.</p>
        )}

        {[...agent.versions]
          .sort((a, b) => parseFloat(b.version) - parseFloat(a.version))
          .map((v) => (
            <VersionRow
              key={v.id}
              version={v}
              agentId={agent.id}
              allTools={tools}
              onRefresh={load}
              canEdit={canEdit}
            />
          ))}
      </div>
    </div>
    </div>
  )
}
