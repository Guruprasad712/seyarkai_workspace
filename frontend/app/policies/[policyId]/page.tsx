"use client"

import { use, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { ChevronDown, ChevronUp, Loader2, Plus, Trash2 } from "lucide-react"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { Button } from "@/components/ui/button"
import type {
  Agent,
  AgentSummary,
  CheckpointOut,
  PolicyOut,
  PublishFailure,
  StageOut,
  User,
} from "@/lib/types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-50"

const selectCls = inputCls

type AgentVersionInfo = { agentName: string; version: string }
type AgentVersionMap = Record<string, AgentVersionInfo>

type PublishedVersionOption = { versionId: string; label: string }

function policyBadge(status: string) {
  if (status === "published")
    return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
  return "bg-muted text-muted-foreground"
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="text-sm">{children}</div>
    </div>
  )
}

function sortedStages(stages: StageOut[]): StageOut[] {
  return [...stages].sort((a, b) => a.sequence - b.sequence)
}

function moveStage(stages: StageOut[], stageId: string, dir: "up" | "down"): string[] {
  const ids = sortedStages(stages).map((s) => s.id)
  const i = ids.indexOf(stageId)
  if (dir === "up" && i > 0) [ids[i - 1], ids[i]] = [ids[i], ids[i - 1]]
  if (dir === "down" && i < ids.length - 1) [ids[i], ids[i + 1]] = [ids[i + 1], ids[i]]
  return ids
}

// ─── Stage form (add / edit) ──────────────────────────────────────────────────

type StageFormProps = {
  policyId: string
  stageId?: string
  prefill?: StageOut
  agentOptions: PublishedVersionOption[]
  onSaved: () => void
  onCancel: () => void
}

function StageForm({ policyId, stageId, prefill, agentOptions, onSaved, onCancel }: StageFormProps) {
  const [name, setName] = useState(prefill?.name ?? "")
  const [description, setDescription] = useState(prefill?.description ?? "")
  const [expectedOutput, setExpectedOutput] = useState(prefill?.expected_output ?? "")
  const [agentVersionId, setAgentVersionId] = useState(prefill?.agent_version_id ?? agentOptions[0]?.versionId ?? "")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    const body = { name, description, expected_output: expectedOutput, agent_version_id: agentVersionId }
    try {
      if (stageId) {
        await apiFetch(`/policies/${policyId}/stages/${stageId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      } else {
        await apiFetch(`/policies/${policyId}/stages`, {
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
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-border p-3">
      <div className="space-y-1">
        <label className="text-xs font-medium">Name</label>
        <input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">Description</label>
        <textarea
          className={inputCls + " min-h-[60px] resize-y"}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">Expected Output</label>
        <textarea
          className={inputCls + " min-h-[60px] resize-y"}
          value={expectedOutput}
          onChange={(e) => setExpectedOutput(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">Agent</label>
        <select
          className={selectCls}
          required
          value={agentVersionId}
          onChange={(e) => setAgentVersionId(e.target.value)}
        >
          <option value="">— select agent —</option>
          {agentOptions.map((opt) => (
            <option key={opt.versionId} value={opt.versionId}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? "Saving…" : stageId ? "Save" : "Add stage"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

// ─── Checkpoint form ──────────────────────────────────────────────────────────

type CheckpointFormProps = {
  policyId: string
  checkpointId?: string
  stageId: string | null
  isFinalReview: boolean
  prefill?: CheckpointOut
  users: User[]
  onSaved: () => void
  onCancel: () => void
}

function CheckpointForm({
  policyId,
  checkpointId,
  stageId,
  isFinalReview,
  prefill,
  users,
  onSaved,
  onCancel,
}: CheckpointFormProps) {
  const [type, setType] = useState<string>(prefill?.type ?? (isFinalReview ? "final_review" : "approval"))
  const [assignedUserId, setAssignedUserId] = useState(prefill?.assigned_user_id ?? users[0]?.id ?? "")
  const [instruction, setInstruction] = useState(prefill?.instruction ?? "")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    const body = {
      type,
      stage_id: stageId,
      assigned_user_id: assignedUserId,
      instruction,
    }
    try {
      if (checkpointId) {
        await apiFetch(`/policies/${policyId}/checkpoints/${checkpointId}`, {
          method: "PATCH",
          body: JSON.stringify({ assigned_user_id: assignedUserId, instruction }),
        })
      } else {
        await apiFetch(`/policies/${policyId}/checkpoints`, {
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
    <form onSubmit={handleSubmit} className="space-y-2 rounded-lg border border-border p-3">
      {!isFinalReview && !checkpointId && (
        <div className="space-y-1">
          <label className="text-xs font-medium">Type</label>
          <select className={selectCls} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="approval">Approval</option>
            <option value="review">Review</option>
            <option value="input">Input</option>
          </select>
        </div>
      )}
      <div className="space-y-1">
        <label className="text-xs font-medium">Assignee</label>
        <select
          className={selectCls}
          required
          value={assignedUserId}
          onChange={(e) => setAssignedUserId(e.target.value)}
        >
          <option value="">— select person —</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name ?? u.email}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium">Instruction</label>
        <textarea
          className={inputCls + " min-h-[60px] resize-y"}
          required
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
        />
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? "Saving…" : checkpointId ? "Save" : "Add"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

// ─── Stage card ───────────────────────────────────────────────────────────────

type StageCardProps = {
  stage: StageOut
  index: number
  total: number
  policy: PolicyOut
  agentVersionMap: AgentVersionMap
  agentOptions: PublishedVersionOption[]
  users: User[]
  readonly: boolean
  onRefresh: () => void
}

function StageCard({
  stage,
  index,
  total,
  policy,
  agentVersionMap,
  agentOptions,
  users,
  readonly,
  onRefresh,
}: StageCardProps) {
  const [editing, setEditing] = useState(false)
  const [addingCheckpoint, setAddingCheckpoint] = useState(false)
  const [editingCheckpointId, setEditingCheckpointId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const checkpoint = policy.checkpoints.find(
    (cp) => cp.stage_id === stage.id && cp.type !== "final_review",
  )
  const agentInfo = agentVersionMap[stage.agent_version_id]

  async function handleMove(dir: "up" | "down") {
    const ids = moveStage(policy.stages, stage.id, dir)
    try {
      await apiFetch(`/policies/${policy.id}/stages/order`, {
        method: "PUT",
        body: JSON.stringify({ stage_ids: ids }),
      })
      onRefresh()
    } catch {
      // silent; UI stays consistent after next refresh
    }
  }

  async function handleDelete() {
    if (checkpoint) {
      if (
        !confirm(
          `Stage "${stage.name}" has a checkpoint. Delete both the stage and its checkpoint?`,
        )
      )
        return
    } else {
      if (!confirm(`Delete stage "${stage.name}"?`)) return
    }
    setDeleting(true)
    try {
      if (checkpoint) {
        await apiFetch(`/policies/${policy.id}/checkpoints/${checkpoint.id}`, { method: "DELETE" })
      }
      await apiFetch(`/policies/${policy.id}/stages/${stage.id}`, { method: "DELETE" })
      onRefresh()
    } catch {
      // ignore; refresh will show current state
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="rounded-lg border border-border">
      {editing ? (
        <div className="p-3">
          <StageForm
            policyId={policy.id}
            stageId={stage.id}
            prefill={stage}
            agentOptions={agentOptions}
            onSaved={() => {
              setEditing(false)
              onRefresh()
            }}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : (
        <div className="p-3">
          <div className="mb-2 flex items-start gap-2">
            <span className="shrink-0 text-xs font-medium text-muted-foreground">
              Stage {stage.sequence}
            </span>
            <span className="flex-1 text-sm font-medium">{stage.name}</span>
            {!readonly && (
              <div className="flex shrink-0 gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={index === 0}
                  onClick={() => handleMove("up")}
                  title="Move up"
                >
                  <ChevronUp className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={index === total - 1}
                  onClick={() => handleMove("down")}
                  title="Move down"
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={deleting}
                  onClick={handleDelete}
                  title="Delete stage"
                >
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
            )}
          </div>

          <div className="space-y-1 text-xs text-muted-foreground">
            {stage.description && <p>{stage.description}</p>}
            <p>
              <span className="font-medium text-foreground">Agent:</span>{" "}
              {agentInfo ? `${agentInfo.agentName} v${agentInfo.version}` : stage.agent_version_id}
            </p>
            {stage.expected_output && (
              <p>
                <span className="font-medium text-foreground">Expected:</span>{" "}
                {stage.expected_output}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Checkpoint panel section ────────────────────────────────────────────────

type CheckpointSectionProps = {
  stage: StageOut
  checkpoint: CheckpointOut | undefined
  policyId: string
  users: User[]
  readonly: boolean
  onRefresh: () => void
}

function CheckpointSection({
  stage,
  checkpoint,
  policyId,
  users,
  readonly,
  onRefresh,
}: CheckpointSectionProps) {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(false)

  const userName = checkpoint
    ? users.find((u) => u.id === checkpoint.assigned_user_id)?.name ??
      users.find((u) => u.id === checkpoint.assigned_user_id)?.email ??
      checkpoint.assigned_user_id
    : null

  async function handleDelete() {
    if (!checkpoint) return
    try {
      await apiFetch(`/policies/${policyId}/checkpoints/${checkpoint.id}`, { method: "DELETE" })
      onRefresh()
    } catch {
      // ignore
    }
  }

  return (
    <div className="rounded-lg border border-border p-3">
      <p className="mb-2 text-xs font-medium">
        Stage {stage.sequence}: {stage.name}
      </p>

      {checkpoint && !editing ? (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground capitalize">{checkpoint.type}</span>
            {" · "}
            {userName}
          </p>
          <p className="text-xs text-muted-foreground">{checkpoint.instruction}</p>
          {!readonly && (
            <div className="mt-2 flex gap-1">
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={() => setEditing(true)}
              >
                Edit
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                onClick={handleDelete}
              >
                Remove
              </Button>
            </div>
          )}
        </div>
      ) : checkpoint && editing ? (
        <CheckpointForm
          policyId={policyId}
          checkpointId={checkpoint.id}
          stageId={stage.id}
          isFinalReview={false}
          prefill={checkpoint}
          users={users}
          onSaved={() => {
            setEditing(false)
            onRefresh()
          }}
          onCancel={() => setEditing(false)}
        />
      ) : adding ? (
        <CheckpointForm
          policyId={policyId}
          stageId={stage.id}
          isFinalReview={false}
          users={users}
          onSaved={() => {
            setAdding(false)
            onRefresh()
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        !readonly && (
          <Button
            type="button"
            variant="ghost"
            size="xs"
            onClick={() => setAdding(true)}
          >
            <Plus className="mr-1 h-3 w-3" />
            Add checkpoint
          </Button>
        )
      )}
    </div>
  )
}

// ─── Final review section ─────────────────────────────────────────────────────

type FinalReviewSectionProps = {
  checkpoint: CheckpointOut | undefined
  policyId: string
  users: User[]
  readonly: boolean
  onRefresh: () => void
}

function FinalReviewSection({
  checkpoint,
  policyId,
  users,
  readonly,
  onRefresh,
}: FinalReviewSectionProps) {
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState(false)

  const userName = checkpoint
    ? users.find((u) => u.id === checkpoint.assigned_user_id)?.name ??
      users.find((u) => u.id === checkpoint.assigned_user_id)?.email ??
      checkpoint.assigned_user_id
    : null

  async function handleDelete() {
    if (!checkpoint) return
    try {
      await apiFetch(`/policies/${policyId}/checkpoints/${checkpoint.id}`, { method: "DELETE" })
      onRefresh()
    } catch {
      // ignore
    }
  }

  return (
    <div className="rounded-lg border border-border p-3">
      <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Final Review
      </p>

      {checkpoint && !editing ? (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Assignee:</span> {userName}
          </p>
          <p className="text-xs text-muted-foreground">{checkpoint.instruction}</p>
          {!readonly && (
            <div className="mt-2 flex gap-1">
              <Button type="button" variant="ghost" size="xs" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button type="button" variant="ghost" size="xs" onClick={handleDelete}>
                Remove
              </Button>
            </div>
          )}
        </div>
      ) : checkpoint && editing ? (
        <CheckpointForm
          policyId={policyId}
          checkpointId={checkpoint.id}
          stageId={null}
          isFinalReview={true}
          prefill={checkpoint}
          users={users}
          onSaved={() => {
            setEditing(false)
            onRefresh()
          }}
          onCancel={() => setEditing(false)}
        />
      ) : adding ? (
        <CheckpointForm
          policyId={policyId}
          stageId={null}
          isFinalReview={true}
          users={users}
          onSaved={() => {
            setAdding(false)
            onRefresh()
          }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        !readonly && (
          <Button type="button" variant="ghost" size="xs" onClick={() => setAdding(true)}>
            <Plus className="mr-1 h-3 w-3" />
            Add Final Review
          </Button>
        )
      )}
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PolicyEditorPage({
  params,
}: {
  params: Promise<{ policyId: string }>
}) {
  const { policyId } = use(params)
  const searchParams = useSearchParams()
  const projectId = searchParams.get("projectId")
  const wiId = searchParams.get("wiId")

  const [policy, setPolicy] = useState<PolicyOut | null>(null)
  const [agentVersionMap, setAgentVersionMap] = useState<AgentVersionMap>({})
  const [agentOptions, setAgentOptions] = useState<PublishedVersionOption[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [publishing, setPublishing] = useState(false)
  const [publishFailures, setPublishFailures] = useState<PublishFailure[]>([])
  const [publishError, setPublishError] = useState("")
  const [addingStage, setAddingStage] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [pol, summaries, activeUsers] = await Promise.all([
        apiFetch<PolicyOut>(`/policies/${policyId}`),
        apiFetch<AgentSummary[]>("/agents"),
        apiFetch<User[]>("/users"),
      ])

      const details = await Promise.all(
        summaries.map((s) => apiFetch<Agent>(`/agents/${s.id}`))
      )

      const vmap: AgentVersionMap = {}
      const opts: PublishedVersionOption[] = []
      for (const agent of details) {
        for (const v of agent.versions ?? []) {
          if (v.status === "published") {
            vmap[v.id] = { agentName: agent.name, version: v.version }
            opts.push({ versionId: v.id, label: `${agent.name} v${v.version}` })
          }
        }
      }

      setPolicy(pol)
      setAgentVersionMap(vmap)
      setAgentOptions(opts)
      setUsers(activeUsers)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load policy")
    } finally {
      setLoading(false)
    }
  }, [policyId])

  const refresh = useCallback(async () => {
    try {
      const pol = await apiFetch<PolicyOut>(`/policies/${policyId}`)
      setPolicy(pol)
    } catch {
      // keep existing state on transient errors
    }
  }, [policyId])

  useEffect(() => {
    load()
  }, [load])

  async function handlePublish() {
    setPublishFailures([])
    setPublishError("")
    setPublishing(true)
    try {
      const pol = await apiFetch<PolicyOut>(`/policies/${policyId}/publish`, { method: "POST" })
      setPolicy(pol)
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const failures = extractPublishFailures(err.body)
        if (failures && failures.length > 0) {
          setPublishFailures(failures)
        } else {
          setPublishError(err.message)
        }
      } else {
        setPublishError(err instanceof ApiError ? err.message : "Publish failed")
      }
    } finally {
      setPublishing(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading policy…
        </div>
      </div>
    )
  }

  if (error || !policy) {
    const backHref =
      projectId && wiId ? `/projects/${projectId}/work-items/${wiId}` : "/projects"
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error || "Policy not found"}
        </div>
        <div className="mt-4">
          <Link href={backHref} className="text-sm text-muted-foreground hover:text-foreground">
            ← Back
          </Link>
        </div>
      </div>
    )
  }

  const readonly = policy.status === "published"
  const stages = sortedStages(policy.stages)
  const finalReviewCheckpoint = policy.checkpoints.find((cp) => cp.type === "final_review")
  const backHref =
    projectId && wiId ? `/projects/${projectId}/work-items/${wiId}` : "/projects"

  // Unique agents used across stages
  const usedVersionIds = [...new Set(stages.map((s) => s.agent_version_id))]

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header bar */}
      <div className="flex shrink-0 items-center gap-4 border-b border-border px-4 py-3">
        <Link href={backHref} className="text-sm text-muted-foreground hover:text-foreground">
          ← Work item
        </Link>

        <div className="flex flex-1 items-center gap-3">
          <span className="text-sm font-semibold">Policy v{policy.version}</span>
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${policyBadge(policy.status)}`}
          >
            {policy.status}
          </span>
          {policy.published_at && (
            <span className="text-xs text-muted-foreground">
              Published {new Date(policy.published_at).toLocaleDateString()}
            </span>
          )}
        </div>

        {!readonly && (
          <Button
            size="sm"
            disabled={publishing}
            onClick={handlePublish}
          >
            {publishing ? (
              <>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                Publishing…
              </>
            ) : (
              "Publish"
            )}
          </Button>
        )}
      </div>

      {/* Three-panel grid */}
      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr_260px] divide-x divide-border">

        {/* Left — Agents */}
        <div className="overflow-y-auto p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Agents
          </p>
          {usedVersionIds.length === 0 ? (
            <p className="text-xs text-muted-foreground">No agents assigned yet.</p>
          ) : (
            <div className="space-y-2">
              {usedVersionIds.map((vId) => {
                const info = agentVersionMap[vId]
                return (
                  <div key={vId} className="rounded-lg border border-border px-3 py-2">
                    <p className="text-sm font-medium">{info?.agentName ?? "Unknown"}</p>
                    <p className="text-xs text-muted-foreground">v{info?.version ?? "?"}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Center — Workflow */}
        <div className="flex flex-col overflow-y-auto p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Workflow
          </p>

          {/* Publish failure banners */}
          {(publishFailures.length > 0 || publishError) && (
            <div className="mb-4 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3">
              <p className="mb-1 text-xs font-medium text-destructive">
                Publish failed — {publishFailures.length > 0 ? `${publishFailures.length} issue${publishFailures.length > 1 ? "s" : ""}` : "error"}
              </p>
              {publishFailures.length > 0 ? (
                <ul className="space-y-0.5">
                  {publishFailures.map((f, i) => (
                    <li key={i} className="text-xs text-destructive">
                      • <span className="font-medium">{f.code}:</span> {f.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-destructive">{publishError}</p>
              )}
            </div>
          )}

          {stages.length === 0 && !addingStage && (
            <div className="mb-4 rounded-lg border border-dashed border-border px-4 py-8 text-center">
              <p className="text-sm text-muted-foreground">No stages yet.</p>
            </div>
          )}

          <div className="space-y-3">
            {stages.map((stage, i) => (
              <StageCard
                key={stage.id}
                stage={stage}
                index={i}
                total={stages.length}
                policy={policy}
                agentVersionMap={agentVersionMap}
                agentOptions={agentOptions}
                users={users}
                readonly={readonly}
                onRefresh={refresh}
              />
            ))}
          </div>

          {addingStage && (
            <div className="mt-3">
              <StageForm
                policyId={policy.id}
                agentOptions={agentOptions}
                onSaved={() => {
                  setAddingStage(false)
                  refresh()
                }}
                onCancel={() => setAddingStage(false)}
              />
            </div>
          )}

          {!readonly && !addingStage && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-3 w-full"
              onClick={() => setAddingStage(true)}
            >
              <Plus className="mr-1.5 h-3.5 w-3.5" />
              Add Stage
            </Button>
          )}
        </div>

        {/* Right — Checkpoints */}
        <div className="overflow-y-auto p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Checkpoints
          </p>

          {stages.length === 0 ? (
            <p className="text-xs text-muted-foreground">Add stages first.</p>
          ) : (
            <div className="space-y-3">
              {stages.map((stage) => {
                const cp = policy.checkpoints.find(
                  (c) => c.stage_id === stage.id && c.type !== "final_review",
                )
                return (
                  <CheckpointSection
                    key={stage.id}
                    stage={stage}
                    checkpoint={cp}
                    policyId={policy.id}
                    users={users}
                    readonly={readonly}
                    onRefresh={refresh}
                  />
                )
              })}
            </div>
          )}

          {/* Final review */}
          <div className="mt-4">
            <FinalReviewSection
              checkpoint={finalReviewCheckpoint}
              policyId={policy.id}
              users={users}
              readonly={readonly}
              onRefresh={refresh}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
