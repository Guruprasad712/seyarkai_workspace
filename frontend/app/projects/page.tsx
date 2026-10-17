"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { apiFetch, ApiError } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { StatusPill } from "@/components/status-pill"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import type { Project } from "@/lib/types"

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

function CreateProjectForm({
  onCreated,
  onCancel,
}: {
  onCreated: () => void
  onCancel: () => void
}) {
  const [name, setName]               = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting]   = useState(false)
  const [nameError, setNameError]     = useState("")
  const [error, setError]             = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setNameError("")
    setError("")
    setSubmitting(true)
    try {
      await apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify({ name, description }),
      })
      onCreated()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setNameError("A project with this name already exists.")
      } else {
        setError(err instanceof ApiError ? err.message : "Failed to create project")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <GlassCard className="mb-6">
      <form onSubmit={handleSubmit} className="space-y-4">
        <h2 className="font-heading text-lg font-bold text-white">New Project</h2>

        <div className="space-y-1.5">
          <label className="text-sm font-medium text-white/80">Name</label>
          <input
            className={inputCls}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Q4 Engineering Review"
          />
          {nameError && <p className="text-xs text-[#EF4444]">{nameError}</p>}
        </div>

        <div className="space-y-1.5">
          <label className="text-sm font-medium text-white/80">Description</label>
          <textarea
            className={inputCls + " min-h-[80px] resize-y"}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
          />
        </div>

        {error && (
          <p className="text-sm text-[#EF4444] bg-[#EF4444]/10 px-3 py-2 rounded-lg border border-[#EF4444]/25">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <BigButton type="submit" variant="gradient" size="md" loading={submitting}>
            Create project
          </BigButton>
          <BigButton type="button" variant="ghost" size="md" onClick={onCancel}>
            Cancel
          </BigButton>
        </div>
      </form>
    </GlassCard>
  )
}

export default function ProjectsPage() {
  const { user } = useAuth()
  const canEdit = can.editProjects(user?.role ?? "")
  const [projects, setProjects]   = useState<Project[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState("")
  const [showCreate, setShowCreate] = useState(false)

  function load() {
    setLoading(true)
    setError("")
    apiFetch<Project[]>("/projects")
      .then(setProjects)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load projects")
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-heading text-4xl font-black text-white">Projects</h1>
            <p className="mt-1.5 text-white/50">
              A shared room for your team and its agents.
            </p>
          </div>
          {!showCreate && canEdit && (
            <BigButton variant="gradient" size="md" onClick={() => setShowCreate(true)}>
              + New Project
            </BigButton>
          )}
        </div>

        {showCreate && (
          <CreateProjectForm
            onCreated={() => { setShowCreate(false); load() }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {loading && <InlineLoader label="Loading projects…" />}

        {error && (
          <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
            {error}
          </div>
        )}

        {!loading && !error && projects.length === 0 && (
          <GlassCard className="text-center py-12">
            <p className="text-white/45 mb-4">No projects yet.</p>
            {canEdit && (
              <BigButton variant="ghost" size="md" onClick={() => setShowCreate(true)}>
                Create your first project
              </BigButton>
            )}
          </GlassCard>
        )}

        {!loading && !error && projects.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <Link key={project.id} href={`/projects/${project.id}`} className="group block">
                <GlassCard className="flex flex-col gap-4 h-full transition-all duration-200 group-hover:bg-white/10 group-hover:border-[#5B6CFF]/40 group-hover:shadow-[0_0_24px_rgba(91,108,255,0.15)]">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="font-heading text-xl font-black text-white leading-snug group-hover:text-white transition-colors">{project.name}</h2>
                    <StatusPill status={project.status} />
                  </div>
                  {project.description ? (
                    <p className="text-sm text-white/60 flex-1">
                      {project.description.length > 90 ? project.description.slice(0, 90) + "…" : project.description}
                    </p>
                  ) : (
                    <p className="text-sm text-white/25 italic flex-1">No description</p>
                  )}
                  <div className="flex items-center justify-between text-xs text-white/40">
                    <span>{project.work_item_count ?? 0} work item{(project.work_item_count ?? 0) !== 1 ? "s" : ""}</span>
                    <span className="font-mono">{new Date(project.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="mt-auto">
                    <div className="w-full flex items-center justify-between rounded-2xl bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF] px-5 py-3 transition-all duration-200 group-hover:opacity-95 group-hover:shadow-[0_0_20px_rgba(91,108,255,0.4)]">
                      <span className="text-[17px] font-black text-white tracking-tight">Enter →</span>
                      <span className="text-white/70 text-sm">Open workspace</span>
                    </div>
                  </div>
                </GlassCard>
              </Link>
            ))}

            {/* Dashed placeholder */}
            {canEdit && (
              <div
                className="flex flex-col items-center justify-center rounded-[var(--radius-xl)] border-2 border-dashed border-white/15 px-6 py-10 cursor-pointer hover:border-white/30 hover:bg-white/3 transition-all duration-200 min-h-[200px]"
                onClick={() => setShowCreate(true)}
              >
                <span className="text-3xl text-white/20 mb-2">+</span>
                <p className="text-sm text-white/35 font-medium">New project</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
