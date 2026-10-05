"use client"

import { use, useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { ChevronDown, ChevronRight, Loader2, Plus, Trash2 } from "lucide-react"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { Button } from "@/components/ui/button"
import type { Agent, AgentVersion, Capability, McpTool, PublishFailure } from "@/lib/types"

// ─── Helpers ────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-50"

const statusColors: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  published: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  retired: "bg-muted/60 text-muted-foreground line-through",
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  inactive: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
}

function Badge({ status }: { status: string }) {
  const cls = statusColors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {status}
    </span>
  )
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
    <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-border p-4">
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
          <label className="text-sm font-medium">Capabilities</label>
          <Button type="button" variant="ghost" size="xs" onClick={addCap}>
            <Plus className="mr-1 h-3 w-3" />
            Add
          </Button>
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
                <Button type="button" variant="ghost" size="icon-sm" onClick={() => removeCap(idx)}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
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
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? "Saving…" : versionId ? "Save changes" : "Add version"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
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
}

function VersionRow({ version, agentId, allTools, onRefresh }: VersionRowProps) {
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
    <div className="rounded-lg border border-border">
      {/* Header row */}
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-medium hover:text-foreground"
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          v{version.version}
        </button>
        <Badge status={version.status} />
        {version.published_at && (
          <span className="text-xs text-muted-foreground">
            {new Date(version.published_at).toLocaleDateString()}
          </span>
        )}
        {toolNames && (
          <span className="text-xs text-muted-foreground">
            Tools: {toolNames}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          {version.status === "draft" && !editing && (
            <>
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={() => setEditing(true)}
              >
                Edit
              </Button>
              <Button
                type="button"
                size="xs"
                disabled={publishing}
                onClick={handlePublish}
              >
                {publishing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  "Publish"
                )}
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Publish failures */}
      {publishFailures.length > 0 && (
        <div className="mx-4 mb-3 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2">
          <p className="mb-1 text-xs font-medium text-destructive">
            Publish validation failed
          </p>
          <ul className="space-y-0.5">
            {publishFailures.map((f) => (
              <li key={f.code} className="text-xs text-destructive">
                <span className="font-medium">{failureLabels[f.code] ?? f.code}:</span>{" "}
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Instructions expand */}
      {expanded && !editing && (
        <div className="border-t border-border px-4 py-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Instructions</p>
          <pre className="whitespace-pre-wrap font-mono text-xs text-foreground">
            {version.instructions}
          </pre>
          {version.capabilities.length > 0 && (
            <>
              <p className="mb-1 mt-3 text-xs font-medium text-muted-foreground">Capabilities</p>
              <ul className="space-y-1">
                {version.capabilities.map((c, i) => (
                  <li key={i} className="text-xs">
                    <span className="font-medium">{c.name}</span>
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
        <div className="border-t border-border p-4">
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
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </div>
    )
  }

  if (error || !agent) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error || "Agent not found"}
        </div>
        <Button className="mt-4" variant="outline" onClick={() => router.push("/agents")}>
          ← Back to agents
        </Button>
      </div>
    )
  }

  const publishedVersion = agent.versions.find((v) => v.status === "published")
  const hasDraft = agent.versions.some((v) => v.status === "draft")

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Back */}
      <div className="mb-6">
        <Link
          href="/agents"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Agent Library
        </Link>
      </div>

      {/* Agent header */}
      <div className="mb-8">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold">{agent.name}</h1>
              <Badge status={agent.status} />
            </div>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">
              {agent.agent_code}
            </p>
          </div>
        </div>
        {agent.description && (
          <p className="mt-3 text-sm text-muted-foreground">{agent.description}</p>
        )}
        {agent.role_purpose && (
          <p className="mt-1 text-sm">
            <span className="text-muted-foreground">Role:</span> {agent.role_purpose}
          </p>
        )}
      </div>

      {/* Versions */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium">Versions</h2>
          {!hasDraft && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAddingVersion(true)}
              disabled={addingVersion}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add version
            </Button>
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
            />
          ))}
      </div>
    </div>
  )
}
