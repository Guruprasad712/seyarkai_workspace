"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Plus } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { Button, buttonVariants } from "@/components/ui/button"
import type { Project } from "@/lib/types"

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-50"

const projectStatusColors: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  inactive: "bg-muted text-muted-foreground",
}

function StatusBadge({ status }: { status: string }) {
  const cls = projectStatusColors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

function CreateProjectForm({
  onCreated,
  onCancel,
}: {
  onCreated: () => void
  onCancel: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [nameError, setNameError] = useState("")
  const [error, setError] = useState("")

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
    <form
      onSubmit={handleSubmit}
      className="mb-6 space-y-4 rounded-lg border border-border p-4"
    >
      <h2 className="text-sm font-medium">New Project</h2>

      <div className="space-y-1">
        <label className="text-sm font-medium">Name</label>
        <input
          className={inputCls}
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Q4 Engineering Review"
        />
        {nameError && <p className="text-xs text-destructive">{nameError}</p>}
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium">Description</label>
        <textarea
          className={inputCls + " min-h-[80px] resize-y"}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Optional"
        />
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={submitting}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
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

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage AI-assisted work items and policy execution.
          </p>
        </div>
        {!showCreate && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            New Project
          </Button>
        )}
      </div>

      {showCreate && (
        <CreateProjectForm
          onCreated={() => {
            setShowCreate(false)
            load()
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {loading && (
        <div className="text-sm text-muted-foreground">Loading…</div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && projects.length === 0 && (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <p className="text-sm text-muted-foreground">No projects yet.</p>
          <Button
            className="mt-4"
            variant="outline"
            onClick={() => setShowCreate(true)}
          >
            Create your first project
          </Button>
        </div>
      )}

      {!loading && !error && projects.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Description</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Work Items</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {projects.map((project, i) => (
                <tr
                  key={project.id}
                  className={i < projects.length - 1 ? "border-b border-border" : ""}
                >
                  <td className="px-4 py-3 font-medium">{project.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {project.description
                      ? project.description.length > 60
                        ? project.description.slice(0, 60) + "…"
                        : project.description
                      : <span className="italic text-muted-foreground/50">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={project.status} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {project.work_item_count}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(project.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/projects/${project.id}`}
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
  )
}
