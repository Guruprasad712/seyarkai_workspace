"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { motion, useReducedMotion } from "motion/react"
import { apiFetch, ApiError } from "@/lib/api"
import { useAuth } from "@/components/auth-provider"
import { GlassCard } from "@/components/glass-card"
import { BigButton, ArrowTile } from "@/components/big-button"

// ─── Types ────────────────────────────────────────────────────────────────────

interface Project {
  id: string
  name: string
  status: string
  work_item_count?: number
  execution_count?: number
}

interface Execution {
  id: string
  execution_number: number
  status: string
  current_stage_id?: string | null
  blocking_checkpoint?: { id: string; assigned_user_id: string; type: string } | null
  work_item_id: string
}

interface KnowledgeDoc {
  id: string
  title: string
  freshness: string
}

// ─── SVG Loom ─────────────────────────────────────────────────────────────────

function LoomSVG() {
  const shouldReduce = useReducedMotion()

  return (
    <svg
      viewBox="0 0 600 200"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="absolute inset-0 w-full h-full opacity-30 pointer-events-none"
      aria-hidden
    >
      {/* Woven threads */}
      {[30, 80, 130, 170].map((y, i) => (
        <motion.path
          key={`h${i}`}
          d={`M 0 ${y} Q 150 ${y - 20} 300 ${y} Q 450 ${y + 20} 600 ${y}`}
          stroke="rgba(255,255,255,0.3)"
          strokeWidth="0.8"
          fill="none"
          initial={shouldReduce ? {} : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.2, delay: i * 0.15, ease: "easeOut" }}
        />
      ))}
      {[80, 200, 320, 440, 520].map((x, i) => (
        <motion.line
          key={`v${i}`}
          x1={x} y1="0" x2={x} y2="200"
          stroke="rgba(255,255,255,0.15)"
          strokeWidth="0.6"
          initial={shouldReduce ? {} : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, delay: 0.6 + i * 0.1, ease: "easeOut" }}
        />
      ))}

      {/* AI node — violet */}
      <motion.circle
        cx="120" cy="100" r="8"
        fill="rgba(196,91,255,0.8)"
        initial={shouldReduce ? {} : { scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 1.0, duration: 0.4 }}
      />
      <circle cx="120" cy="100" r="14" stroke="rgba(196,91,255,0.25)" strokeWidth="1.5" fill="none"/>

      {/* Thread connecting AI → checkpoint */}
      <motion.path
        d="M 128 100 Q 220 90 290 100"
        stroke="rgba(91,108,255,0.5)"
        strokeWidth="1.2"
        fill="none"
        initial={shouldReduce ? {} : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ delay: 1.2, duration: 0.5 }}
      />

      {/* Checkpoint node — diamond — teal */}
      <motion.path
        d="M 300 85 L 315 100 L 300 115 L 285 100 Z"
        fill="rgba(0,220,200,0.8)"
        initial={shouldReduce ? {} : { scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 1.5, duration: 0.4 }}
      />
      <path d="M 300 78 L 322 100 L 300 122 L 278 100 Z" stroke="rgba(0,220,200,0.25)" strokeWidth="1.5" fill="none"/>

      {/* Thread checkpoint → human */}
      <motion.path
        d="M 315 100 Q 390 110 470 100"
        stroke="rgba(255,122,200,0.5)"
        strokeWidth="1.2"
        fill="none"
        initial={shouldReduce ? {} : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ delay: 1.7, duration: 0.5 }}
      />

      {/* Human node — pink */}
      <motion.circle
        cx="480" cy="100" r="8"
        fill="rgba(255,122,200,0.8)"
        initial={shouldReduce ? {} : { scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 2.0, duration: 0.4 }}
      />
      <circle cx="480" cy="100" r="14" stroke="rgba(255,122,200,0.25)" strokeWidth="1.5" fill="none"/>
    </svg>
  )
}

// ─── Home Page ────────────────────────────────────────────────────────────────

export default function HomePage() {
  const { user } = useAuth()
  const [projects, setProjects]           = useState<Project[]>([])
  const [staleCount, setStaleCount]       = useState(0)
  const [agentCount, setAgentCount]       = useState(0)
  const [pendingCps, setPendingCps]       = useState<{ label: string; href: string }[]>([])
  const [liveExec, setLiveExec]           = useState<{ label: string; href: string; progress?: number } | null>(null)
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)

  const greeting = (() => {
    const h = new Date().getHours()
    if (h < 12) return "Good morning"
    if (h < 18) return "Good afternoon"
    return "Good evening"
  })()

  useEffect(() => {
    // Backend health
    apiFetch<{ status: string }>("/health")
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false))

    // Projects
    apiFetch<Project[]>("/projects")
      .then(setProjects)
      .catch(() => {})

    // Knowledge stale count
    apiFetch<KnowledgeDoc[]>("/knowledge/documents")
      .then((docs) => setStaleCount(docs.filter((d) => d.freshness === "stale").length))
      .catch(() => {})

    // Agents published count
    apiFetch<{ items?: unknown[] }>("/agents")
      .then((res) => {
        const items = Array.isArray(res) ? res : (res as { items?: unknown[] }).items ?? []
        setAgentCount(items.length)
      })
      .catch(() => {})
  }, [])

  // Scan executions for attention + live strips
  useEffect(() => {
    if (projects.length === 0) return
    const allExecs: Promise<Execution[]>[] = projects.map((p) =>
      apiFetch<{ items: Execution[] }>(`/projects/${p.id}/executions`)
        .then((r) => r.items ?? [])
        .catch(() => [] as Execution[])
    )
    Promise.all(allExecs).then((groups) => {
      const all = groups.flat()
      const myId = user?.id
      const cps = all
        .filter((e) => e.status === "waiting_for_approval" && e.blocking_checkpoint &&
          (e.blocking_checkpoint.assigned_user_id === myId || !myId))
        .slice(0, 3)
        .map((e) => ({
          label: `Review checkpoint · Execution #${e.execution_number}`,
          href: `/executions/${e.id}`,
        }))
      setPendingCps(cps)

      const running = all.find((e) => e.status === "running")
      if (running) {
        setLiveExec({
          label: `Execution #${running.execution_number}`,
          href: `/executions/${running.id}`,
        })
      }
    })
  }, [projects, user?.id])

  return (
    <div className="min-h-screen bg-[#070A14]">
      {/* Faint static bg gradient */}
      <div
        className="pointer-events-none fixed inset-0 overflow-hidden"
        aria-hidden
        style={{
          background:
            "radial-gradient(ellipse 80% 50% at 50% -20%, rgba(91,108,255,0.07) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 mx-auto max-w-6xl px-4 py-10 space-y-12">

        {/* ── Tamil hero ──────────────────────────────────────────────────────── */}
        <div className="relative flex flex-col items-center text-center py-8 rounded-[var(--radius-xl)]">
          <LoomSVG />
          <div className="relative z-10 space-y-3">
            <div
              className="font-tamil text-7xl md:text-8xl font-black pb-4"
              style={{
                background: "linear-gradient(135deg, rgba(255,255,255,0.85) 0%, rgba(196,91,255,0.7) 50%, rgba(0,220,200,0.8) 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                lineHeight: 1.2,
              }}
            >
              செயற்கை
            </div>
            <div className="font-heading text-2xl font-bold text-white/80 tracking-wide">Seyarkai</div>
            <p className="text-white/45 text-sm">Intelligence, made by us. Governed by you.</p>
          </div>
        </div>

        {/* ── Greeting + heading ───────────────────────────────────────────────── */}
        <div>
          <p className="text-sm font-semibold text-[#00DCC8] mb-1">
            {greeting}{user?.name ? `, ${user.name}` : ""}
          </p>
          <h1 className="font-heading text-4xl md:text-5xl font-black text-white leading-tight">
            What should we<br className="hidden sm:block" /> execute today?
          </h1>
        </div>

        {/* ── Three cards ─────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Projects */}
          <GlassCard
            className="flex flex-col gap-4 hover:bg-white/8 transition-colors duration-200"
            style={{ background: "rgba(91,108,255,0.08)" } as React.CSSProperties}
          >
            <div>
              <h2 className="font-heading text-xl font-bold text-white">Projects</h2>
              <p className="text-sm text-white/55 mt-1">Work items, policies and live executions.</p>
            </div>
            <p className="text-sm text-white/50">
              {projects.length > 0 ? `${projects.length} active` : "No projects yet"}
            </p>
            <Link href="/projects" className="mt-auto">
              <BigButton variant="ghost" size="md" className="w-full justify-between">
                <span>Open Projects</span>
                <ArrowTile color="indigo" />
              </BigButton>
            </Link>
          </GlassCard>

          {/* Knowledge */}
          <GlassCard
            className="flex flex-col gap-4 hover:bg-white/8 transition-colors duration-200"
            style={{ background: "rgba(0,220,200,0.06)" } as React.CSSProperties}
          >
            <div>
              <h2 className="font-heading text-xl font-bold text-white">Knowledge</h2>
              <p className="text-sm text-white/55 mt-1">Company Brain with freshness checks.</p>
            </div>
            {staleCount > 0 ? (
              <p className="text-sm font-semibold text-[#FF7AC8]">{staleCount} stale document{staleCount !== 1 ? "s" : ""}</p>
            ) : (
              <p className="text-sm text-white/50">All documents fresh</p>
            )}
            <Link href="/knowledge" className="mt-auto">
              <BigButton variant="ghost" size="md" className="w-full justify-between">
                <span>Open Knowledge</span>
                <ArrowTile color="teal" />
              </BigButton>
            </Link>
          </GlassCard>

          {/* Agents */}
          <GlassCard
            className="flex flex-col gap-4 hover:bg-white/8 transition-colors duration-200"
            style={{ background: "rgba(196,91,255,0.08)" } as React.CSSProperties}
          >
            <div>
              <h2 className="font-heading text-xl font-bold text-white">Agents</h2>
              <p className="text-sm text-white/55 mt-1">Reusable AI workers and their tools.</p>
            </div>
            <p className="text-sm text-white/50">
              {agentCount > 0 ? `${agentCount} published` : "No agents yet"}
            </p>
            <Link href="/agents" className="mt-auto">
              <BigButton variant="ghost" size="md" className="w-full justify-between">
                <span>Open Agents</span>
                <ArrowTile color="violet" />
              </BigButton>
            </Link>
          </GlassCard>
        </div>

        {/* ── Attention + Live strips ──────────────────────────────────────────── */}
        {(pendingCps.length > 0 || liveExec) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Needs your attention */}
            {pendingCps.length > 0 && (
              <GlassCard glow="pink" padding={false} className="p-5 space-y-3">
                <p className="text-xs font-bold uppercase tracking-widest text-[#FF7AC8]">
                  Needs your attention
                </p>
                {pendingCps.map((cp, i) => (
                  <Link
                    key={i}
                    href={cp.href}
                    className="flex items-center justify-between gap-3 rounded-xl bg-white/5 px-4 py-3 hover:bg-white/10 transition-colors"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="h-2 w-2 rounded-full bg-[#FF7AC8] shrink-0 animate-pulse" />
                      <span className="text-sm text-white/80">{cp.label}</span>
                    </div>
                    <span className="text-sm text-[#FF7AC8] shrink-0">Open →</span>
                  </Link>
                ))}
              </GlassCard>
            )}

            {/* Live now */}
            {liveExec && (
              <GlassCard glow="teal" padding={false} className="p-5 space-y-3">
                <p className="text-xs font-bold uppercase tracking-widest text-[#00DCC8]">
                  Live now
                </p>
                <Link href={liveExec.href} className="block space-y-3 hover:opacity-90 transition-opacity">
                  <p className="text-base font-semibold text-white">{liveExec.label}</p>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-[#00DCC8] to-[#5B6CFF] animate-pulse"
                      style={{ width: "48%" }}
                    />
                  </div>
                </Link>
              </GlassCard>
            )}
          </div>
        )}

        {/* Backend status footer */}
        {backendOnline === false && (
          <p className="text-xs text-[#EF4444] text-center">
            Backend offline — some data may be unavailable
          </p>
        )}
      </div>
    </div>
  )
}
