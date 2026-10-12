"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { Plus } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { buttonVariants } from "@/components/ui/button"
import type { AgentSummary } from "@/lib/types"

const statusColors: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  active: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
  inactive: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
}

function StatusBadge({ status }: { status: string }) {
  const cls = statusColors[status] ?? "bg-muted text-muted-foreground"
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  )
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    apiFetch<AgentSummary[]>("/agents")
      .then(setAgents)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load agents")
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Agent Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage AI agents and their published versions.
          </p>
        </div>
        <Link href="/agents/new" className={buttonVariants()}>
          <Plus className="mr-1.5 h-4 w-4" />
          New Agent
        </Link>
      </div>

      {loading && (
        <div className="text-sm text-muted-foreground">Loading…</div>
      )}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && agents.length === 0 && (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <p className="text-sm text-muted-foreground">No agents yet.</p>
          <Link
            href="/agents/new"
            className={`mt-4 ${buttonVariants({ variant: "outline" })}`}
          >
            Create your first agent
          </Link>
        </div>
      )}

      {!loading && !error && agents.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Code</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Role / Purpose</th>
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {agents.map((agent, i) => (
                <tr
                  key={agent.id}
                  className={i < agents.length - 1 ? "border-b border-border" : ""}
                >
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {agent.agent_code}
                  </td>
                  <td className="px-4 py-3 font-medium">{agent.name}</td>
                  <td className="px-4 py-3 text-muted-foreground">{agent.role_purpose}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={agent.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/agents/${agent.id}`}
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
