"use client"

import { useEffect, useState } from "react"
import { CheckCircle, Clock, AlertTriangle, Plus, RefreshCw } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import type { KnowledgeDocument } from "@/lib/types"

// ─── Freshness helpers ────────────────────────────────────────────────────────

const freshnessConfig = {
  fresh: {
    label: "Fresh",
    icon: CheckCircle,
    cls: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    iconCls: "text-green-500",
  },
  ageing: {
    label: "Ageing",
    icon: Clock,
    cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
    iconCls: "text-yellow-500",
  },
  stale: {
    label: "Stale",
    icon: AlertTriangle,
    cls: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
    iconCls: "text-red-500",
  },
}

function FreshnessBadge({ freshness }: { freshness: KnowledgeDocument["freshness"] }) {
  const cfg = freshnessConfig[freshness]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cfg.cls}`}>
      <Icon className={`h-3 w-3 ${cfg.iconCls}`} />
      {cfg.label}
    </span>
  )
}

// ─── Add document form ────────────────────────────────────────────────────────

function AddDocForm({ onAdded }: { onAdded: (doc: KnowledgeDocument) => void }) {
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [source, setSource] = useState("")
  const [content, setContent] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

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
      setTitle("")
      setSource("")
      setContent("")
      setOpen(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to add document")
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <Button onClick={() => setOpen(true)}>
        <Plus className="mr-1.5 h-4 w-4" />
        Add Document
      </Button>
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-border bg-card p-4 space-y-3"
    >
      <h3 className="font-medium text-sm">New Knowledge Document</h3>

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Title</label>
          <input
            className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Document title"
            required
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">Source</label>
          <input
            className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={source}
            onChange={e => setSource(e.target.value)}
            placeholder="URL or reference"
            required
          />
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Content</label>
        <textarea
          className="w-full rounded border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          rows={4}
          value={content}
          onChange={e => setContent(e.target.value)}
          placeholder="Document content…"
          required
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? "Adding…" : "Add"}
        </Button>
      </div>
    </form>
  )
}

// ─── Document row ─────────────────────────────────────────────────────────────

function DocRow({
  doc,
  onVerified,
}: {
  doc: KnowledgeDocument
  onVerified: (updated: KnowledgeDocument) => void
}) {
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState("")

  async function handleVerify() {
    setError("")
    setVerifying(true)
    try {
      const updated = await apiFetch<KnowledgeDocument>(`/knowledge/${doc.id}/verify`, {
        method: "POST",
      })
      onVerified(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verify failed")
    } finally {
      setVerifying(false)
    }
  }

  return (
    <tr className="border-t border-border hover:bg-muted/30 transition-colors">
      <td className="px-4 py-3">
        <p className="font-medium text-sm">{doc.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{doc.content}</p>
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground max-w-[180px]">
        <span className="truncate block" title={doc.source}>{doc.source}</span>
      </td>
      <td className="px-4 py-3">
        <FreshnessBadge freshness={doc.freshness} />
        <p className="text-xs text-muted-foreground mt-1">{doc.age_days}d ago</p>
      </td>
      <td className="px-4 py-3 text-right">
        {error && <p className="text-xs text-destructive mb-1">{error}</p>}
        <Button
          variant="outline"
          size="sm"
          onClick={handleVerify}
          disabled={verifying}
          className="text-xs"
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${verifying ? "animate-spin" : ""}`} />
          {verifying ? "Verifying…" : "Verify"}
        </Button>
      </td>
    </tr>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KnowledgeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    apiFetch<KnowledgeDocument[]>("/knowledge")
      .then(setDocs)
      .catch(err => setError(err instanceof ApiError ? err.message : "Failed to load"))
      .finally(() => setLoading(false))
  }, [])

  function handleAdded(doc: KnowledgeDocument) {
    setDocs(prev => [doc, ...prev])
  }

  function handleVerified(updated: KnowledgeDocument) {
    setDocs(prev => prev.map(d => d.id === updated.id ? updated : d))
  }

  const freshCount = docs.filter(d => d.freshness === "fresh").length
  const ageingCount = docs.filter(d => d.freshness === "ageing").length
  const staleCount = docs.filter(d => d.freshness === "stale").length

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Company Brain</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Knowledge documents injected into agent stage tasks.
          </p>
        </div>
        <AddDocForm onAdded={handleAdded} />
      </div>

      {!loading && !error && docs.length > 0 && (
        <div className="mb-6 flex gap-4">
          {[
            { label: "Fresh", count: freshCount, cls: "text-green-600 dark:text-green-400" },
            { label: "Ageing", count: ageingCount, cls: "text-yellow-600 dark:text-yellow-400" },
            { label: "Stale", count: staleCount, cls: "text-red-600 dark:text-red-400" },
          ].map(({ label, count, cls }) => (
            <div key={label} className="rounded-lg border border-border bg-card px-4 py-3 text-center min-w-[80px]">
              <p className={`text-xl font-semibold ${cls}`}>{count}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && docs.length === 0 && (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <p className="text-sm text-muted-foreground">No documents yet. Add one to get started.</p>
        </div>
      )}

      {!loading && !error && docs.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Document</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Source</th>
                <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">Freshness</th>
                <th className="px-4 py-2.5 text-right text-xs font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(doc => (
                <DocRow key={doc.id} doc={doc} onVerified={handleVerified} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
