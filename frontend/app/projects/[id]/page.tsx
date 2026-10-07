"use client"

import { use, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { Loader2, Plus } from "lucide-react"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { Button, buttonVariants } from "@/components/ui/button"
import type { Agent, AgentSummary, Project, User, WorkItem } from "@/lib/types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-50"

const projectStatusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  inactive: "bg-muted text-muted-foreground",
}

const wiStatusColors: Record<string, string> = {
  new: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  running: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
}

function Badge({ status, colors }: { status: string; colors: Record<string, string> }) {
  const cls = colors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

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
  const [name, setName] = useState("")
  const [objective, setObjective] = useState("")
  const [description, setDescription] = useState("")
  const [expectedOutcome, setExpectedOutcome] = useState("")
  const [aiOptions, setAiOptions] = useState<WorkerOption[]>([])
  const [humanOptions, setHumanOptions] = useState<WorkerOption[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loadingWorkers, setLoadingWorkers] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [nameError, setNameError] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    Promise.all([
      apiFetch<AgentSummary[]>("/agents"),
      apiFetch<User[]>("/users"),
    ]).then(async ([summaries, users]) => {
      // Fetch each agent detail to find published versions (N+1 but list is small)
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
        label: u.name ?? u.email,
      }))
      setAiOptions(ai)
      setHumanOptions(human)
    }).catch(() => {
      // non-fatal; user sees empty lists
    }).finally(() => setLoadingWorkers(false))
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
    <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-border p-4">
      <h3 className="text-sm font-medium">New Work Item</h3>

      <div className="space-y-1">
        <label className="text-sm font-medium">Name</label>
        <input
          className={inputCls}
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        {nameError && <p className="text-xs text-destructive">{nameError}</p>}
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Objective</label>
        <input
          className={inputCls}
          required
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          placeholder="One-line goal"
        />
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Description</label>
        <textarea
          className={inputCls + " min-h-[80px] resize-y"}
          required
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Expected Outcome</label>
        <textarea
          className={inputCls + " min-h-[80px] resize-y"}
          required
          value={expectedOutcome}
          onChange={(e) => setExpectedOutcome(e.target.value)}
        />
      </div>

      {/* Workers */}
      <div>
        <label className="mb-2 block text-sm font-medium">Workers</label>
        {loadingWorkers ? (
          <p className="text-sm text-muted-foreground">Loading workers…</p>
        ) : (
          <div className="space-y-3">
            {aiOptions.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">AI Agents</p>
                <div className="space-y-1.5">
                  {aiOptions.map((opt) => (
                    <label
                      key={opt.id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 hover:bg-muted/40"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(opt.id)}
                        onChange={() => toggleWorker(opt.id)}
                      />
                      <span className="text-sm">{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {humanOptions.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">People</p>
                <div className="space-y-1.5">
                  {humanOptions.map((opt) => (
                    <label
                      key={opt.id}
                      className="flex cursor-pointer items-center gap-3 rounded-lg border border-border px-3 py-2 hover:bg-muted/40"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(opt.id)}
                        onChange={() => toggleWorker(opt.id)}
                      />
                      <span className="text-sm">{opt.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {aiOptions.length === 0 && humanOptions.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No published agents or active users found.
              </p>
            )}
          </div>
        )}
        {selectedIds.size === 0 && !loadingWorkers && (
          <p className="mt-1 text-xs text-muted-foreground">Select at least one worker.</p>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!canSubmit}>
          {submitting ? "Creating…" : "Create work item"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)

  const [project, setProject] = useState<Project | null>(null)
  const [workItems, setWorkItems] = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
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

  if (error || !project) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error || "Project not found"}
        </div>
        <div className="mt-4">
          <Link href="/projects" className="text-sm text-muted-foreground hover:text-foreground">
            ← Back to projects
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      {/* Back */}
      <div className="mb-6">
        <Link href="/projects" className="text-sm text-muted-foreground hover:text-foreground">
          ← Projects
        </Link>
      </div>

      {/* Project header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          <Badge status={project.status} colors={projectStatusColors} />
        </div>
        {project.description && (
          <p className="mt-2 text-sm text-muted-foreground">{project.description}</p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Created {new Date(project.created_at).toLocaleDateString()}
        </p>
      </div>

      {/* Work items section */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium">Work Items</h2>
          {!showCreateWI && (
            <Button size="sm" onClick={() => setShowCreateWI(true)}>
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              New Work Item
            </Button>
          )}
        </div>

        {showCreateWI && (
          <div className="mb-6">
            <CreateWorkItemForm
              projectId={id}
              onCreated={() => {
                setShowCreateWI(false)
                load()
              }}
              onCancel={() => setShowCreateWI(false)}
            />
          </div>
        )}

        {workItems.length === 0 && !showCreateWI && (
          <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
            <p className="text-sm text-muted-foreground">No work items yet.</p>
            <Button
              className="mt-3"
              variant="outline"
              size="sm"
              onClick={() => setShowCreateWI(true)}
            >
              Create the first work item
            </Button>
          </div>
        )}

        {workItems.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Objective</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Workers</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {workItems.map((wi, i) => (
                  <tr
                    key={wi.id}
                    className={i < workItems.length - 1 ? "border-b border-border" : ""}
                  >
                    <td className="px-4 py-3 font-medium">{wi.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {wi.objective.length > 60
                        ? wi.objective.slice(0, 60) + "…"
                        : wi.objective}
                    </td>
                    <td className="px-4 py-3">
                      <Badge status={wi.status} colors={wiStatusColors} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {wi.workers.map(workerLabel).join(", ") || "—"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(wi.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/projects/${id}/work-items/${wi.id}`}
                        className={buttonVariants({ variant: "ghost", size: "sm" })}
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
