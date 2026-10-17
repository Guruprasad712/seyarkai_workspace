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
import type { AgentSummary } from "@/lib/types"

export default function AgentsPage() {
  const { user } = useAuth()
  const canEdit = can.editAgents(user?.role ?? "")
  const [agents, setAgents]   = useState<AgentSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState("")

  useEffect(() => {
    apiFetch<AgentSummary[]>("/agents")
      .then(setAgents)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Failed to load agents")
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-heading text-4xl font-black text-white">Agent Library</h1>
            <p className="mt-1.5 text-white/50">Manage AI agents and their published versions.</p>
          </div>
          {canEdit && (
            <Link href="/agents/new">
              <BigButton variant="gradient" size="md">+ New Agent</BigButton>
            </Link>
          )}
        </div>

        {loading && <InlineLoader label="Loading agents…" />}

        {error && (
          <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
            {error}
          </div>
        )}

        {!loading && !error && agents.length === 0 && (
          <GlassCard className="text-center py-12">
            <p className="text-white/40 mb-4">No agents yet.</p>
            {canEdit && (
              <Link href="/agents/new">
                <BigButton variant="ghost" size="md">Create your first agent</BigButton>
              </Link>
            )}
          </GlassCard>
        )}

        {!loading && !error && agents.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map((agent) => (
              <GlassCard
                key={agent.id}
                className="flex flex-col gap-3 hover:bg-white/8 transition-colors duration-200"
                style={{ background: "rgba(0,220,200,0.05)" } as React.CSSProperties}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="font-heading text-lg font-bold text-white leading-snug">{agent.name}</h2>
                    <p className="font-mono text-xs text-[#00DCC8]/70 mt-0.5">{agent.agent_code}</p>
                  </div>
                  <StatusPill status={agent.status} />
                </div>
                <p className="text-sm text-white/55 flex-1">{agent.role_purpose}</p>
                <Link href={`/agents/${agent.id}`} className="mt-auto">
                  <BigButton variant="ghost" size="md" className="w-full justify-between">
                    <span>View Agent</span>
                    <span className="text-white/50">→</span>
                  </BigButton>
                </Link>
              </GlassCard>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
