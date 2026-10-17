"use client"

import { useEffect, useState } from "react"
import { apiFetch, ApiError } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { FreshnessBadge } from "@/components/freshness-badge"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import type { KnowledgeDocument } from "@/lib/types"

// ─── Add document form ────────────────────────────────────────────────────────

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

function AddDocForm({ onAdded, canWrite }: { onAdded: (doc: KnowledgeDocument) => void; canWrite: boolean }) {
  const [open, setOpen]       = useState(false)
  const [title, setTitle]     = useState("")
  const [source, setSource]   = useState("")
  const [content, setContent] = useState("")
  const [saving, setSaving]   = useState(false)
  const [error, setError]     = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSaving(true)
    try {
      const doc = await apiFetch<KnowledgeDocument>("/knowledge", {
        method: "POST",
        body: JSON.stringify({ title, source, content }),
      })
      onAdded(doc)
      setTitle(""); setSource(""); setContent(""); setOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add document")
    } finally {
      setSaving(false)
    }
  }

  if (!canWrite) return null

  if (!open) {
    return (
      <BigButton variant="gradient" size="md" onClick={() => setOpen(true)}>
        + Add Document
      </BigButton>
    )
  }

  return (
    <GlassCard>
      <form onSubmit={handleSubmit} className="space-y-4">
        <h3 className="font-heading text-lg font-bold text-white">New Knowledge Document</h3>
        {error && <p className="text-xs text-[#EF4444]">{error}</p>}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-white/70">Title</label>
            <input className={inputCls} value={title} onChange={e => setTitle(e.target.value)} placeholder="Document title" required />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-white/70">Source</label>
            <input className={inputCls} value={source} onChange={e => setSource(e.target.value)} placeholder="URL or reference" required />
          </div>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-white/70">Content</label>
          <textarea className={inputCls + " min-h-[100px] resize-y"} rows={4} value={content} onChange={e => setContent(e.target.value)} placeholder="Document content…" required />
        </div>
        <div className="flex justify-end gap-2">
          <BigButton type="button" variant="ghost" size="md" onClick={() => setOpen(false)}>Cancel</BigButton>
          <BigButton type="submit" variant="gradient" size="md" loading={saving}>Add</BigButton>
        </div>
      </form>
    </GlassCard>
  )
}

// ─── Document card ────────────────────────────────────────────────────────────

function DocCard({ doc, onVerified, canWrite }: { doc: KnowledgeDocument; onVerified: (updated: KnowledgeDocument) => void; canWrite: boolean }) {
  const [verifying, setVerifying] = useState(false)
  const [error, setError]         = useState("")

  async function handleVerify() {
    setError("")
    setVerifying(true)
    try {
      const updated = await apiFetch<KnowledgeDocument>(`/knowledge/${doc.id}/verify`, { method: "POST" })
      onVerified(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verify failed")
    } finally {
      setVerifying(false)
    }
  }

  const isStale = doc.freshness === "stale"

  return (
    <GlassCard glow={isStale ? "pink" : "none"} className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-heading text-base font-bold text-white leading-snug">{doc.title}</p>
          <p className="text-xs text-white/35 mt-0.5 truncate">{doc.source}</p>
        </div>
        <FreshnessBadge freshness={doc.freshness} age_days={doc.age_days} />
      </div>

      <p className="text-sm text-white/50 line-clamp-2">{doc.content}</p>

      <div className="flex items-center justify-between mt-auto">
        <span className="font-mono text-xs text-white/25">{doc.age_days}d ago</span>
        {error && <p className="text-xs text-[#EF4444]">{error}</p>}
        {canWrite && (
          <BigButton variant={isStale ? "gradient" : "ghost"} size="sm" loading={verifying} onClick={handleVerify}>
            {verifying ? "Verifying…" : "Verify"}
          </BigButton>
        )}
      </div>
    </GlassCard>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const { user } = useAuth()
  const canWrite = can.addKnowledge(user?.role ?? "")
  const [docs, setDocs]     = useState<KnowledgeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState("")

  useEffect(() => {
    apiFetch<KnowledgeDocument[]>("/knowledge")
      .then(setDocs)
      .catch(err => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [])

  const freshCount  = docs.filter(d => d.freshness === "fresh").length
  const ageingCount = docs.filter(d => d.freshness === "ageing").length
  const staleCount  = docs.filter(d => d.freshness === "stale").length

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-6xl px-4 py-10">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-heading text-4xl font-black text-white">Company Brain</h1>
            <p className="mt-1.5 text-white/50">Your agents are only as good as what they read. Is it still true?</p>
          </div>
          <AddDocForm onAdded={(doc) => setDocs(prev => [doc, ...prev])} canWrite={canWrite} />
        </div>

        {/* Freshness summary */}
        {!loading && !error && docs.length > 0 && (
          <div className="mb-6 flex gap-3">
            {[
              { label: "Fresh",   count: freshCount,  color: "#22C55E" },
              { label: "Ageing",  count: ageingCount, color: "#F59E0B" },
              { label: "Stale",   count: staleCount,  color: "#EF4444" },
            ].map(({ label, count, color }) => (
              <div key={label} className="glass rounded-xl px-5 py-3 text-center min-w-[80px]">
                <p className="text-2xl font-black" style={{ color }}>{count}</p>
                <p className="text-xs text-white/40 mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        )}

        {loading && <InlineLoader label="Loading knowledge base…" />}

        {error && (
          <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
            {error}
          </div>
        )}

        {!loading && !error && docs.length === 0 && (
          <GlassCard className="text-center py-12">
            <p className="text-white/40">No documents yet. Add one to get started.</p>
          </GlassCard>
        )}

        {!loading && !error && docs.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {docs.map(doc => (
              <DocCard key={doc.id} doc={doc} canWrite={canWrite} onVerified={(updated) => setDocs(prev => prev.map(d => d.id === updated.id ? updated : d))} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
