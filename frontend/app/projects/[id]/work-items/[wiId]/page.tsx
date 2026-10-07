"use client"

import { use, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Loader2, Sparkles } from "lucide-react"
import { apiFetch, ApiError, extractPublishFailures } from "@/lib/api"
import { Button } from "@/components/ui/button"
import type { WorkItem } from "@/lib/types"

// ─── Helpers ─────────────────────────────────────────────────────────────────

const wiStatusColors: Record<string, string> = {
  new: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  running: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
  completed: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
}

function StatusBadge({ status }: { status: string }) {
  const cls = wiStatusColors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="text-sm">{children}</div>
    </div>
  )
}

type GenerateResult =
  | { kind: "draft_exists" }
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

  const [workItem, setWorkItem] = useState<WorkItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [generating, setGenerating] = useState(false)
  const [generateResult, setGenerateResult] = useState<GenerateResult | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const wi = await apiFetch<WorkItem>(`/work-items/${wiId}`)
      setWorkItem(wi)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load work item")
    } finally {
      setLoading(false)
    }
  }, [wiId])

  useEffect(() => {
    load()
  }, [load])

  async function handleGeneratePolicy() {
    setGenerateResult(null)
    setGenerating(true)
    try {
      const policy = await apiFetch<{ id: string }>(`/work-items/${wiId}/policies/generate`, {
        method: "POST",
      })
      router.push(`/policies/${policy.id}?projectId=${projectId}&wiId=${wiId}`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setGenerateResult({ kind: "draft_exists" })
      } else if (err instanceof ApiError && err.status === 422) {
        const failures = extractPublishFailures(err.body)
        if (failures && failures.length > 0) {
          setGenerateResult({ kind: "failures", messages: failures.map((f) => f.message) })
        } else {
          setGenerateResult({ kind: "error", message: err.message })
        }
      } else {
        setGenerateResult({
          kind: "error",
          message: err instanceof ApiError ? err.message : "Generation failed",
        })
      }
    } finally {
      setGenerating(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      </div>
    )
  }

  if (error || !workItem) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error || "Work item not found"}
        </div>
        <div className="mt-4">
          <Link
            href={`/projects/${projectId}`}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            ← Back to project
          </Link>
        </div>
      </div>
    )
  }

  const hasAiWorker = workItem.workers.some((w) => w.type === "ai_agent")

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Back */}
      <div className="mb-6">
        <Link
          href={`/projects/${projectId}`}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← {projectId ? "Project" : "Projects"}
        </Link>
      </div>

      {/* Header */}
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{workItem.name}</h1>
            <StatusBadge status={workItem.status} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Created {new Date(workItem.created_at).toLocaleDateString()}
          </p>
        </div>

        {/* Generate Policy button */}
        {hasAiWorker && (
          <div className="shrink-0">
            <Button
              onClick={handleGeneratePolicy}
              disabled={generating}
              variant="outline"
            >
              {generating ? (
                <>
                  <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  Generating…
                </>
              ) : (
                <>
                  <Sparkles className="mr-1.5 h-4 w-4" />
                  Generate Policy
                </>
              )}
            </Button>
          </div>
        )}
      </div>

      {/* Generate result banners */}
      {generateResult && (
        <div className="mb-6">
          {generateResult.kind === "draft_exists" && (
            <div className="rounded-lg border border-amber-300/60 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-700/40 dark:bg-amber-900/20 dark:text-amber-300">
              A draft policy already exists for this work item.
            </div>
          )}
          {generateResult.kind === "failures" && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3">
              <p className="mb-1 text-xs font-medium text-destructive">Generation validation failed</p>
              <ul className="space-y-0.5">
                {generateResult.messages.map((m, i) => (
                  <li key={i} className="text-xs text-destructive">{m}</li>
                ))}
              </ul>
            </div>
          )}
          {generateResult.kind === "error" && (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              Generation failed — {generateResult.message}
            </div>
          )}
        </div>
      )}

      {/* Work item fields */}
      <div className="space-y-6">
        <Field label="OBJECTIVE">
          <p>{workItem.objective}</p>
        </Field>

        <Field label="DESCRIPTION">
          <p className="whitespace-pre-wrap">{workItem.description}</p>
        </Field>

        <Field label="EXPECTED OUTCOME">
          <p className="whitespace-pre-wrap">{workItem.expected_outcome}</p>
        </Field>

        {/* Workers */}
        <div>
          <p className="mb-2 text-xs font-medium text-muted-foreground">WORKERS</p>
          {workItem.workers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No workers assigned.</p>
          ) : (
            <div className="space-y-2">
              {workItem.workers.map((w, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
                >
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${
                      w.type === "ai_agent"
                        ? "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {w.type === "ai_agent" ? "AI" : "Human"}
                  </span>
                  <div>
                    {w.type === "ai_agent" ? (
                      <>
                        <span className="text-sm font-medium">{w.agent_name ?? "Agent"}</span>
                        {w.agent_version && (
                          <span className="ml-1.5 text-xs text-muted-foreground">
                            v{w.agent_version}
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        <span className="text-sm font-medium">{w.user_name ?? w.user_email ?? "User"}</span>
                        {w.user_email && w.user_name && (
                          <span className="ml-1.5 text-xs text-muted-foreground">{w.user_email}</span>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
