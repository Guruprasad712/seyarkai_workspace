"use client"

import { use, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
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
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"
const selectCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white bg-[rgba(7,10,20,0.7)] outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50"

type AgentVersionInfo = { agentName: string; version: string }
type AgentVersionMap = Record<string, AgentVersionInfo>
type PublishedVersionOption = { versionId: string; label: string }

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

// ─── Stage form ───────────────────────────────────────────────────────────────

type StageFormProps = {
  policyId: string
  stageId?: string
  prefill?: StageOut
  agentOptions: PublishedVersionOption[]
  onSaved: () => void
  onCancel: () => void
}

function StageForm({ policyId, stageId, prefill, agentOptions, onSaved, onCancel }: StageFormProps) {
  const [name, setName]               = useState(prefill?.name ?? "")
  const [description, setDescription] = useState(prefill?.description ?? "")
  const [expectedOutput, setExpectedOutput] = useState(prefill?.expected_output ?? "")
  const [agentVersionId, setAgentVersionId] = useState(prefill?.agent_version_id ?? agentOptions[0]?.versionId ?? "")
  const [submitting, setSubmitting]   = useState(false)
  const [error, setError]             = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    const body = { name, description, expected_output: expectedOutput, agent_version_id: agentVersionId }
    try {
      if (stageId) {
        await apiFetch(`/policies/${policyId}/stages/${stageId}`, { method: "PATCH", body: JSON.stringify(body) })
      } else {
        await apiFetch(`/policies/${policyId}/stages`, { method: "POST", body: JSON.stringify(body) })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 p-4 rounded-xl bg-white/5 border border-white/10">
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-white/70">Name</label>
        <input className={inputCls} required value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-white/70">Description</label>
        <textarea className={inputCls + " min-h-[60px] resize-y"} value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-white/70">Expected Output</label>
        <textarea className={inputCls + " min-h-[60px] resize-y"} value={expectedOutput} onChange={(e) => setExpectedOutput(e.target.value)} />
      </div>
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-white/70">Agent</label>
        <select className={selectCls} required value={agentVersionId} onChange={(e) => setAgentVersionId(e.target.value)}>
          <option value="">— select agent —</option>
          {agentOptions.map((opt) => (
            <option key={opt.versionId} value={opt.versionId}>{opt.label}</option>
          ))}
        </select>
      </div>
      {error && <p className="text-xs text-[#EF4444]">{error}</p>}
      <div className="flex gap-2">
        <BigButton type="submit" variant="gradient" size="sm" loading={submitting}>
          {stageId ? "Save" : "Add stage"}
        </BigButton>
        <BigButton type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</BigButton>
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

function CheckpointForm({ policyId, checkpointId, stageId, isFinalReview, prefill, users, onSaved, onCancel }: CheckpointFormProps) {
  const [type, setType]                 = useState<string>(prefill?.type ?? (isFinalReview ? "final_review" : "approval"))
  const [assignedUserId, setAssignedUserId] = useState(prefill?.assigned_user_id ?? users[0]?.id ?? "")
  const [instruction, setInstruction]   = useState(prefill?.instruction ?? "")
  const [submitting, setSubmitting]     = useState(false)
  const [error, setError]               = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSubmitting(true)
    const body = { type, stage_id: stageId, assigned_user_id: assignedUserId, instruction }
    try {
      if (checkpointId) {
        await apiFetch(`/policies/${policyId}/checkpoints/${checkpointId}`, { method: "PATCH", body: JSON.stringify({ assigned_user_id: assignedUserId, instruction }) })
      } else {
        await apiFetch(`/policies/${policyId}/checkpoints`, { method: "POST", body: JSON.stringify(body) })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 p-3 rounded-xl bg-[#FF7AC8]/5 border border-[#FF7AC8]/15">
      {!isFinalReview && !checkpointId && (
        <div className="space-y-1">
          <label className="text-xs font-medium text-white/70">Type</label>
          <select className={selectCls} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="approval">Approval</option>
            <option value="review">Review</option>
            <option value="input">Input</option>
          </select>
        </div>
      )}
      <div className="space-y-1">
        <label className="text-xs font-medium text-white/70">Assignee</label>
        <select className={selectCls} required value={assignedUserId} onChange={(e) => setAssignedUserId(e.target.value)}>
          <option value="">— select person —</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>{u.name ?? u.email}</option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium text-white/70">Instruction</label>
        <textarea className={inputCls + " min-h-[60px] resize-y"} required value={instruction} onChange={(e) => setInstruction(e.target.value)} />
      </div>
      {error && <p className="text-xs text-[#EF4444]">{error}</p>}
      <div className="flex gap-2">
        <BigButton type="submit" variant="gradient" size="sm" loading={submitting}>
          {checkpointId ? "Save" : "Add"}
        </BigButton>
        <BigButton type="button" variant="ghost" size="sm" onClick={onCancel}>Cancel</BigButton>
      </div>
    </form>
  )
}

// ─── Stage card ───────────────────────────────────────────────────────────────

function StageCard({
  stage, index, total, policy, agentVersionMap, agentOptions, users, readonly, onRefresh,
}: {
  stage: StageOut; index: number; total: number; policy: PolicyOut
  agentVersionMap: AgentVersionMap; agentOptions: PublishedVersionOption[]
  users: User[]; readonly: boolean; onRefresh: () => void
}) {
  const [editing, setEditing]     = useState(false)
  const [addingCp, setAddingCp]   = useState(false)
  const [editCpId, setEditCpId]   = useState<string | null>(null)
  const [deleting, setDeleting]   = useState(false)

  const checkpoint = policy.checkpoints.find((cp) => cp.stage_id === stage.id && cp.type !== "final_review")
  const agentInfo  = agentVersionMap[stage.agent_version_id]

  async function handleMove(dir: "up" | "down") {
    const ids = moveStage(policy.stages, stage.id, dir)
    try {
      await apiFetch(`/policies/${policy.id}/stages/order`, { method: "PUT", body: JSON.stringify({ stage_ids: ids }) })
      onRefresh()
    } catch { /* silent */ }
  }

  async function handleDelete() {
    if (checkpoint) {
      if (!confirm(`Stage "${stage.name}" has a checkpoint. Delete both?`)) return
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
    } catch { /* ignore */ } finally { setDeleting(false) }
  }

  // Stage type colour: by position/agent presence
  const borderColor = checkpoint ? "#FF7AC8" : "#00DCC8"

  return (
    <div className="glass rounded-xl overflow-hidden" style={{ borderLeft: `3px solid ${borderColor}` }}>
      {editing ? (
        <div className="p-3">
          <StageForm
            policyId={policy.id}
            stageId={stage.id}
            prefill={stage}
            agentOptions={agentOptions}
            onSaved={() => { setEditing(false); onRefresh() }}
            onCancel={() => setEditing(false)}
          />
        </div>
      ) : (
        <div className="p-4">
          <div className="flex items-start gap-2 mb-2">
            <span className="text-[10px] font-bold text-white/35 uppercase tracking-widest shrink-0 mt-0.5">
              {stage.sequence}
            </span>
            <span className="flex-1 text-sm font-semibold text-white">{stage.name}</span>
            {!readonly && (
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-white/10 text-white/50 hover:text-white disabled:opacity-30 transition-colors"
                  disabled={index === 0}
                  onClick={() => handleMove("up")}
                  title="Move up"
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-white/10 text-white/50 hover:text-white disabled:opacity-30 transition-colors"
                  disabled={index === total - 1}
                  onClick={() => handleMove("down")}
                  title="Move down"
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="px-2 h-7 rounded-lg text-xs text-white/50 hover:text-white hover:bg-white/10 transition-colors"
                  onClick={() => setEditing(true)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="px-2 h-7 rounded-lg text-xs text-[#EF4444]/70 hover:text-[#EF4444] hover:bg-[#EF4444]/10 transition-colors disabled:opacity-30"
                  disabled={deleting}
                  onClick={handleDelete}
                  title="Delete stage"
                >
                  ✕
                </button>
              </div>
            )}
          </div>

          <div className="space-y-1 text-xs text-white/50">
            {stage.description && <p>{stage.description}</p>}
            <p>
              <span className="font-medium text-[#00DCC8]">Agent:</span>{" "}
              {agentInfo ? `${agentInfo.agentName} v${agentInfo.version}` : stage.agent_version_id}
            </p>
            {stage.expected_output && (
              <p>
                <span className="font-medium text-white/65">Expected:</span>{" "}
                {stage.expected_output}
              </p>
            )}
          </div>

          {/* Checkpoint sub-section */}
          {checkpoint && !editCpId && (
            <div className="mt-3 rounded-lg bg-[#FF7AC8]/8 border border-[#FF7AC8]/15 px-3 py-2 space-y-1">
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-sm bg-[#FF7AC8] rotate-45 shrink-0" />
                <span className="text-xs font-semibold text-[#FF7AC8] capitalize">{checkpoint.type.replace(/_/g, " ")} checkpoint</span>
              </div>
              <p className="text-xs text-white/50">{checkpoint.instruction}</p>
              {!readonly && (
                <div className="flex gap-1 pt-1">
                  <button className="text-xs text-white/40 hover:text-white transition-colors" onClick={() => setEditCpId(checkpoint.id)}>Edit</button>
                  <span className="text-white/20">·</span>
                  <button className="text-xs text-[#EF4444]/60 hover:text-[#EF4444] transition-colors"
                    onClick={async () => {
                      try { await apiFetch(`/policies/${policy.id}/checkpoints/${checkpoint.id}`, { method: "DELETE" }); onRefresh() } catch { /* ignore */ }
                    }}
                  >Remove</button>
                </div>
              )}
            </div>
          )}
          {editCpId && (
            <div className="mt-3">
              <CheckpointForm
                policyId={policy.id}
                checkpointId={editCpId}
                stageId={stage.id}
                isFinalReview={false}
                prefill={checkpoint}
                users={users}
                onSaved={() => { setEditCpId(null); onRefresh() }}
                onCancel={() => setEditCpId(null)}
              />
            </div>
          )}
          {!checkpoint && !addingCp && !readonly && (
            <button
              type="button"
              className="mt-2 text-xs text-[#FF7AC8]/60 hover:text-[#FF7AC8] transition-colors"
              onClick={() => setAddingCp(true)}
            >
              + Add checkpoint
            </button>
          )}
          {addingCp && (
            <div className="mt-3">
              <CheckpointForm
                policyId={policy.id}
                stageId={stage.id}
                isFinalReview={false}
                users={users}
                onSaved={() => { setAddingCp(false); onRefresh() }}
                onCancel={() => setAddingCp(false)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Final review ─────────────────────────────────────────────────────────────

function FinalReviewSection({ checkpoint, policyId, users, readonly, onRefresh }: {
  checkpoint: CheckpointOut | undefined; policyId: string; users: User[]
  readonly: boolean; onRefresh: () => void
}) {
  const [adding, setAdding]   = useState(false)
  const [editing, setEditing] = useState(false)

  const userName = checkpoint
    ? users.find((u) => u.id === checkpoint.assigned_user_id)?.name ??
      users.find((u) => u.id === checkpoint.assigned_user_id)?.email ??
      checkpoint.assigned_user_id
    : null

  return (
    <div className="glass rounded-xl p-4 border-l-2 border-[#C45BFF]">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[#C45BFF] mb-3">Final Review</p>
      {checkpoint && !editing ? (
        <div className="space-y-1">
          <p className="text-xs text-white/60">
            <span className="text-[#C45BFF]">Assignee:</span> {userName}
          </p>
          <p className="text-xs text-white/50">{checkpoint.instruction}</p>
          {!readonly && (
            <div className="flex gap-2 pt-1">
              <button className="text-xs text-white/40 hover:text-white transition-colors" onClick={() => setEditing(true)}>Edit</button>
              <button className="text-xs text-[#EF4444]/60 hover:text-[#EF4444] transition-colors"
                onClick={async () => {
                  try { await apiFetch(`/policies/${policyId}/checkpoints/${checkpoint.id}`, { method: "DELETE" }); onRefresh() } catch { /* ignore */ }
                }}
              >Remove</button>
            </div>
          )}
        </div>
      ) : checkpoint && editing ? (
        <CheckpointForm policyId={policyId} checkpointId={checkpoint.id} stageId={null} isFinalReview prefill={checkpoint} users={users} onSaved={() => { setEditing(false); onRefresh() }} onCancel={() => setEditing(false)} />
      ) : adding ? (
        <CheckpointForm policyId={policyId} stageId={null} isFinalReview users={users} onSaved={() => { setAdding(false); onRefresh() }} onCancel={() => setAdding(false)} />
      ) : (
        !readonly && (
          <button type="button" className="text-xs text-[#C45BFF]/60 hover:text-[#C45BFF] transition-colors" onClick={() => setAdding(true)}>
            + Add Final Review
          </button>
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
  const wiId      = searchParams.get("wiId")
  const { user } = useAuth()

  const [policy, setPolicy]           = useState<PolicyOut | null>(null)
  const [agentVersionMap, setAgentVersionMap] = useState<AgentVersionMap>({})
  const [agentOptions, setAgentOptions]       = useState<PublishedVersionOption[]>([])
  const [users, setUsers]             = useState<User[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState("")
  const [publishing, setPublishing]   = useState(false)
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
        apiFetch<User[]>(wiId ? `/users/directory?eligible_for=${wiId}` : "/users/directory"),
      ])
      const details = await Promise.all(summaries.map((s) => apiFetch<Agent>(`/agents/${s.id}`)))
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
    } catch { /* keep existing */ }
  }, [policyId])

  useEffect(() => { load() }, [load])

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
        if (failures && failures.length > 0) setPublishFailures(failures)
        else setPublishError(err.message)
      } else {
        setPublishError(err instanceof ApiError ? err.message : "Publish failed")
      }
    } finally {
      setPublishing(false)
    }
  }

  if (loading) return <InlineLoader label="Loading policy…" />

  if (error || !policy) {
    const backHref = projectId && wiId ? `/projects/${projectId}/work-items/${wiId}` : "/projects"
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
          {error || "Policy not found"}
        </div>
        <Link href={backHref} className="mt-4 inline-block text-sm text-white/45 hover:text-white transition-colors">← Back</Link>
      </div>
    )
  }

  const readonly = policy.status === "published" || !can.editPolicy(user?.role ?? "")
  const stages   = sortedStages(policy.stages)
  const finalReviewCheckpoint = policy.checkpoints.find((cp) => cp.type === "final_review")
  const backHref = projectId && wiId ? `/projects/${projectId}/work-items/${wiId}` : "/projects"
  const usedVersionIds = [...new Set(stages.map((s) => s.agent_version_id))]

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#070A14]">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-4 border-b border-white/8 bg-[rgba(7,10,20,0.9)] backdrop-blur-xl px-5 py-3">
        <Link href={backHref} className="text-sm text-white/45 hover:text-white transition-colors">
          ← Work item
        </Link>
        <div className="flex flex-1 items-center gap-3">
          <span className="font-heading font-semibold text-white">Policy v{policy.version}</span>
          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wide ${
            policy.status === "published" ? "bg-[#22C55E]/15 text-[#22C55E]" : "bg-white/10 text-white/55"
          }`}>
            {policy.status}
          </span>
          {policy.published_at && (
            <span className="font-mono text-xs text-white/30">
              Published {new Date(policy.published_at).toLocaleDateString()}
            </span>
          )}
        </div>
        {policy.status !== "published" && can.publishPolicy(user?.role ?? "") && (
          <BigButton variant="gradient" size="md" loading={publishing} onClick={handlePublish}>
            Publish
          </BigButton>
        )}
      </div>

      {/* Three-panel grid */}
      <div className="grid min-h-0 flex-1 grid-cols-[200px_1fr_260px] divide-x divide-white/8">

        {/* Left — Agents */}
        <div className="overflow-y-auto px-4 py-5">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-white/30">Agents</p>
          {usedVersionIds.length === 0 ? (
            <p className="text-xs text-white/35">No agents assigned yet.</p>
          ) : (
            <div className="space-y-2">
              {usedVersionIds.map((vId) => {
                const info = agentVersionMap[vId]
                return (
                  <div key={vId} className="rounded-xl glass px-3 py-2.5">
                    <p className="text-sm font-medium text-white/85">{info?.agentName ?? "Unknown"}</p>
                    <p className="font-mono text-xs text-[#00DCC8]/70">v{info?.version ?? "?"}</p>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Center — Workflow */}
        <div className="flex flex-col overflow-y-auto px-5 py-5">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-white/30">Workflow</p>

          {(publishFailures.length > 0 || publishError) && (
            <div className="mb-4 rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3">
              <p className="mb-1 text-xs font-bold text-[#EF4444]">
                Publish failed — {publishFailures.length > 0 ? `${publishFailures.length} issue${publishFailures.length > 1 ? "s" : ""}` : "error"}
              </p>
              {publishFailures.length > 0 ? (
                <ul className="space-y-0.5">
                  {publishFailures.map((f, i) => (
                    <li key={i} className="text-xs text-[#EF4444]/85">• <span className="font-medium">{f.code}:</span> {f.message}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-[#EF4444]/85">{publishError}</p>
              )}
            </div>
          )}

          {stages.length === 0 && !addingStage && (
            <div className="mb-4 rounded-xl border-2 border-dashed border-white/15 px-4 py-8 text-center">
              <p className="text-sm text-white/35">No stages yet.</p>
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
                onSaved={() => { setAddingStage(false); refresh() }}
                onCancel={() => setAddingStage(false)}
              />
            </div>
          )}

          {!readonly && !addingStage && (
            <button
              type="button"
              className="mt-3 w-full flex items-center justify-center gap-2 py-3 rounded-xl border-2 border-dashed border-white/15 text-sm text-white/40 hover:text-white hover:border-white/30 hover:bg-white/3 transition-all"
              onClick={() => setAddingStage(true)}
            >
              + Add Stage
            </button>
          )}
        </div>

        {/* Right — Checkpoints */}
        <div className="overflow-y-auto px-4 py-5">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-white/30">Checkpoints</p>

          {stages.length === 0 ? (
            <p className="text-xs text-white/35">Add stages first.</p>
          ) : (
            <div className="space-y-3">
              {stages.map((stage) => {
                const cp = policy.checkpoints.find((c) => c.stage_id === stage.id && c.type !== "final_review")
                const userName = cp
                  ? users.find((u) => u.id === cp.assigned_user_id)?.name ??
                    users.find((u) => u.id === cp.assigned_user_id)?.email ??
                    cp.assigned_user_id
                  : null

                return (
                  <GlassCard key={stage.id} padding={false} className={`text-xs ${cp ? "border-[#FF7AC8]/20" : ""}`}>
                    <div className="px-4 py-3">
                      <p className="text-[11px] font-semibold text-white/70 mb-2">
                        Stage {stage.sequence}: {stage.name}
                      </p>
                      {cp ? (
                        <div className="space-y-0.5">
                          <p className="text-[#FF7AC8] font-medium capitalize">{cp.type.replace(/_/g, " ")}</p>
                          <p className="text-white/45">{userName}</p>
                          <p className="text-white/40">{cp.instruction}</p>
                          {!readonly && (
                            <div className="flex gap-2 pt-1">
                              <button className="text-[10px] text-white/35 hover:text-white transition-colors"
                                onClick={async () => {
                                  try { await apiFetch(`/policies/${policy.id}/checkpoints/${cp.id}`, { method: "DELETE" }); refresh() } catch { /* ignore */ }
                                }}
                              >Remove</button>
                            </div>
                          )}
                        </div>
                      ) : (
                        <p className="text-white/25 italic">No checkpoint</p>
                      )}
                    </div>
                  </GlassCard>
                )
              })}
            </div>
          )}

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
