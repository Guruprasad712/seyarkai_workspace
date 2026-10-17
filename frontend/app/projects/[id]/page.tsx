"use client"

import { use, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { StatusPill } from "@/components/status-pill"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import type { Agent, AgentSummary, Project, User, WorkItem } from "@/lib/types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

function workerLabel(w: WorkItem["workers"][number]): string {
  if (w.type === "ai_agent") {
    return w.agent_name ? `${w.agent_name} v${w.agent_version}` : "AI Agent"
  }
  return w.user_name ?? w.user_email ?? "Human"
}

// ─── Work item create form ────────────────────────────────────────────────────

type WorkerOption =
  | { kind: "ai"; id: string; label: string }
  | { kind: "human"; id: string; label: string }

type CreateWorkItemFormProps = {
  projectId: string
  onCreated: () => void
  onCancel: () => void
}

function CreateWorkItemForm({ projectId, onCreated, onCancel }: CreateWorkItemFormProps) {
  const [name, setName]                     = useState("")
  const [objective, setObjective]           = useState("")
  const [description, setDescription]       = useState("")
  const [expectedOutcome, setExpectedOutcome] = useState("")
  const [aiOptions, setAiOptions]           = useState<WorkerOption[]>([])
  const [humanOptions, setHumanOptions]     = useState<WorkerOption[]>([])
  const [selectedIds, setSelectedIds]       = useState<Set<string>>(new Set())
  const [loadingWorkers, setLoadingWorkers] = useState(true)
  const [submitting, setSubmitting]         = useState(false)
  const [nameError, setNameError]           = useState("")
  const [error, setError]                   = useState("")

  useEffect(() => {
    Promise.all([
      apiFetch<AgentSummary[]>("/agents"),
      apiFetch<{ id: string; name: string; role: string }[]>("/users/directory"),
    ]).then(async ([summaries, users]) => {
      const details = await Promise.all(
        summaries.map((s) => apiFetch<Agent>(`/agents/${s.id}`))
      )
      const ai: WorkerOption[] = []
      for (const agent of details) {
        const pub = (agent.versions ?? []).find((v) => v.status === "published")
        if (pub) {
          ai.push({ kind: "ai", id: pub.id, label: `${agent.name} v${pub.version}` })
        }
      }
      const human: WorkerOption[] = users.map((u) => ({
        kind: "human",
        id: u.id,
        label: u.name,
      }))
      setAiOptions(ai)
      setHumanOptions(human)
    }).catch(() => {}).finally(() => setLoadingWorkers(false))
  }, [])

  function toggleWorker(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const canSubmit = selectedIds.size > 0 && !submitting

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setNameError("")
    setError("")
    setSubmitting(true)
    const allOptions = [...aiOptions, ...humanOptions]
    const workers = Array.from(selectedIds).map((id) => {
      const opt = allOptions.find((o) => o.id === id)!
      return { type: opt.kind === "ai" ? "ai_agent" : "human", id }
    })
    try {
      await apiFetch(`/projects/${projectId}/work-items`, {
        method: "POST",
        body: JSON.stringify({ name, objective, description, expected_outcome: expectedOutcome, workers }),
      })
      onCreated()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNameError("A work item with this name already exists in this project.")
      } else if (err instanceof ApiError && err.status === 422) {
        const failures = extractPublishFailures(err.body)
        if (failures && failures.length > 0) {
          setError(failures.map((f) => f.message).join("; "))
        } else {
          setError(err.message)
        }
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to create work item")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <GlassCard className="mb-6">
      <form onSubmit={handleSubmit} className="space-y-4">
        <h3 className="font-heading text-lg font-bold text-white">New Work Item</h3>

        {[
          { label: "Name",            value: name,            setter: setName,           type: "text", required: true, placeholder: "" },
          { label: "Objective",       value: objective,       setter: setObjective,      type: "text", required: true, placeholder: "One-line goal" },
        ].map(({ label, value, setter, type, required, placeholder }) => (
          <div key={label} className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">{label}</label>
            <input
              className={inputCls}
              type={type}
              required={required}
              value={value}
              onChange={(e) => setter(e.target.value)}
              placeholder={placeholder}
            />
            {label === "Name" && nameError && <p className="text-xs text-[#EF4444]">{nameError}</p>}
          </div>
        ))}

        {[
          { label: "Description",      value: description,      setter: setDescription },
          { label: "Expected Outcome", value: expectedOutcome,  setter: setExpectedOutcome },
        ].map(({ label, value, setter }) => (
          <div key={label} className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">{label}</label>
            <textarea
              className={inputCls + " min-h-[80px] resize-y"}
              required
              value={value}
              onChange={(e) => setter(e.target.value)}
            />
          </div>
        ))}

        {/* Workers */}
        <div>
          <label className="mb-2 block text-sm font-medium text-white/80">Workers</label>
          {loadingWorkers ? (
            <p className="text-sm text-white/40">Loading workers…</p>
          ) : (
            <div className="space-y-3">
              {aiOptions.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[#00DCC8]/80">AI Agents</p>
                  <div className="space-y-2">
                    {aiOptions.map((opt) => (
                      <label
                        key={opt.id}
                        className="flex cursor-pointer items-center gap-3 rounded-xl glass px-4 py-2.5 hover:bg-white/10 transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={selectedIds.has(opt.id)}
                          onChange={() => toggleWorker(opt.id)}
                          className="accent-[#5B6CFF]"
                        />
                        <span className="text-sm text-white/80">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {humanOptions.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[#FF7AC8]/80">People</p>
                  <div className="space-y-2">
                    {humanOptions.map((opt) => (
                      <label
                        key={opt.id}
                        className="flex cursor-pointer items-center gap-3 rounded-xl glass px-4 py-2.5 hover:bg-white/10 transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={selectedIds.has(opt.id)}
                          onChange={() => toggleWorker(opt.id)}
                          className="accent-[#5B6CFF]"
                        />
                        <span className="text-sm text-white/80">{opt.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
              {aiOptions.length === 0 && humanOptions.length === 0 && (
                <p className="text-sm text-white/40">No published agents or active users found.</p>
              )}
            </div>
          )}
          {selectedIds.size === 0 && !loadingWorkers && (
            <p className="mt-1.5 text-xs text-white/35">Select at least one worker.</p>
          )}
        </div>

        {error && (
          <p className="text-sm text-[#EF4444] bg-[#EF4444]/10 px-3 py-2 rounded-lg border border-[#EF4444]/25">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <BigButton type="submit" variant="gradient" size="md" disabled={!canSubmit} loading={submitting}>
            Create work item
          </BigButton>
          <BigButton type="button" variant="ghost" size="md" onClick={onCancel}>
            Cancel
          </BigButton>
        </div>
      </form>
    </GlassCard>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const { user } = useAuth()
  const canEdit = can.editProjects(user?.role ?? "")

  const [project, setProject]     = useState<Project | null>(null)
  const [workItems, setWorkItems] = useState<WorkItem[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState("")
  const [showCreateWI, setShowCreateWI] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [proj, wis] = await Promise.all([
        apiFetch<Project>(`/projects/${id}`),
        apiFetch<WorkItem[]>(`/projects/${id}/work-items`),
      ])
      setProject(proj)
      setWorkItems(wis)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load project")
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) return <InlineLoader label="Loading project…" />

  if (error || !project) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
          {error || "Project not found"}
        </div>
        <Link href="/projects" className="mt-4 inline-block text-sm text-white/50 hover:text-white transition-colors">
          ← Back to projects
        </Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <Link href="/projects" className="text-sm text-white/45 hover:text-white transition-colors">
          ← Projects
        </Link>

        {/* Project header */}
        <div className="mt-6 mb-8">
          <div className="flex items-center gap-3">
            <h1 className="font-heading text-4xl font-black text-white">{project.name}</h1>
            <StatusPill status={project.status} />
          </div>
          {project.description && (
            <p className="mt-2 text-white/55">{project.description}</p>
          )}
          <p className="mt-1 font-mono text-xs text-white/30">
            Created {new Date(project.created_at).toLocaleDateString()}
          </p>
        </div>

        {/* Work items section */}
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-heading text-2xl font-bold text-white">Work Items</h2>
            {!showCreateWI && canEdit && (
              <BigButton variant="gradient" size="md" onClick={() => setShowCreateWI(true)}>
                + New Work Item
              </BigButton>
            )}
          </div>

          {showCreateWI && (
            <CreateWorkItemForm
              projectId={id}
              onCreated={() => { setShowCreateWI(false); load() }}
              onCancel={() => setShowCreateWI(false)}
            />
          )}

          {workItems.length === 0 && !showCreateWI && (
            <GlassCard className="text-center py-10">
              <p className="text-white/40 mb-4">No work items yet.</p>
              {canEdit && (
                <BigButton variant="ghost" size="md" onClick={() => setShowCreateWI(true)}>
                  Create the first work item
                </BigButton>
              )}
            </GlassCard>
          )}

          {workItems.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {workItems.map((wi) => (
                <GlassCard key={wi.id} className="flex flex-col gap-3 hover:bg-white/8 transition-colors duration-200">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-heading text-base font-bold text-white leading-snug">{wi.name}</h3>
                    <StatusPill status={wi.status} />
                  </div>
                  <p className="text-sm text-white/55">
                    {wi.objective.length > 80 ? wi.objective.slice(0, 80) + "…" : wi.objective}
                  </p>
                  {wi.workers.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {wi.workers.map((w, i) => (
                        <span
                          key={i}
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                            w.type === "ai_agent"
                              ? "bg-[#00DCC8]/15 text-[#00DCC8]"
                              : "bg-[#FF7AC8]/15 text-[#FF7AC8]"
                          }`}
                        >
                          {workerLabel(w)}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center justify-between mt-auto">
                    <span className="font-mono text-xs text-white/30">
                      {new Date(wi.created_at).toLocaleDateString()}
                    </span>
                    <Link href={`/projects/${id}/work-items/${wi.id}`}>
                      <BigButton variant="ghost" size="sm">
                        View / Enter →
                      </BigButton>
                    </Link>
                  </div>
                </GlassCard>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
