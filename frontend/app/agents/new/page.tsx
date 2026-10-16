"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { Plus, Trash2 } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import type { Agent, Capability, McpTool } from "@/lib/types"

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

function Field({
  label,
  error,
  children,
}: {
  label: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-white/80">{label}</label>
      {children}
      {error && <p className="text-xs text-[#EF4444]">{error}</p>}
    </div>
  )
}

export default function NewAgentPage() {
  const router = useRouter()

  const [tools, setTools] = useState<McpTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(true)

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [rolePurpose, setRolePurpose] = useState("")
  const [instructions, setInstructions] = useState("")
  const [capabilities, setCapabilities] = useState<Capability[]>([
    { name: "", description: "" },
  ])
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set())

  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [generalError, setGeneralError] = useState("")

  useEffect(() => {
    apiFetch<McpTool[]>("/mcp-tools")
      .then((ts) => setTools(ts.filter((t) => t.status === "active")))
      .catch(() => {})
      .finally(() => setToolsLoading(false))
  }, [])

  function addCapability() {
    setCapabilities((prev) => [...prev, { name: "", description: "" }])
  }

  function removeCapability(idx: number) {
    setCapabilities((prev) => prev.filter((_, i) => i !== idx))
  }

  function updateCapability(idx: number, field: keyof Capability, value: string) {
    setCapabilities((prev) =>
      prev.map((c, i) => (i === idx ? { ...c, [field]: value } : c)),
    )
  }

  function toggleTool(id: string) {
    setSelectedTools((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFieldErrors({})
    setGeneralError("")
    setSubmitting(true)

    const body = {
      name,
      description,
      role_purpose: rolePurpose,
      instructions,
      capabilities: capabilities.filter((c) => c.name.trim()),
      tool_ids: Array.from(selectedTools),
    }

    try {
      const agent = await apiFetch<Agent>("/agents", {
        method: "POST",
        body: JSON.stringify(body),
      })
      router.push(`/agents/${agent.id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ name: "An agent with this name already exists." })
        } else {
          setGeneralError(err.message)
        }
      } else {
        setGeneralError("Unexpected error")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-2xl px-4 py-10">
        <div className="mb-6">
          <Link href="/agents" className="text-sm text-white/45 hover:text-white transition-colors">
            ← Agent Library
          </Link>
          <h1 className="font-heading mt-4 text-4xl font-black text-white">New Agent</h1>
          <p className="mt-1.5 text-white/50">
            Create an agent and its first draft version.
          </p>
        </div>

        <GlassCard>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Name */}
            <Field label="Name" error={fieldErrors.name}>
              <input
                className={inputCls}
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Research Analyst"
              />
            </Field>

            {/* Description */}
            <Field label="Description">
              <textarea
                className={inputCls + " min-h-[72px] resize-y"}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this agent do?"
              />
            </Field>

            {/* Role / Purpose */}
            <Field label="Role / Purpose">
              <input
                className={inputCls}
                value={rolePurpose}
                onChange={(e) => setRolePurpose(e.target.value)}
                placeholder="One-line summary of the agent's role"
              />
            </Field>

            {/* Instructions */}
            <Field label="Instructions (version 1.0)">
              <textarea
                className={inputCls + " min-h-[120px] resize-y font-mono text-xs"}
                required
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="System prompt / instructions for this agent…"
              />
            </Field>

            {/* Capabilities */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-sm font-medium text-white/80">Capabilities</label>
                <button
                  type="button"
                  onClick={addCapability}
                  className="flex items-center gap-1 text-xs text-[#5B6CFF] hover:text-[#C45BFF] transition-colors"
                >
                  <Plus className="h-3 w-3" />
                  Add
                </button>
              </div>
              <div className="space-y-2">
                {capabilities.map((cap, idx) => (
                  <div key={idx} className="flex gap-2">
                    <input
                      placeholder="Name"
                      className={inputCls + " flex-1"}
                      required={idx === 0}
                      value={cap.name}
                      onChange={(e) => updateCapability(idx, "name", e.target.value)}
                    />
                    <input
                      placeholder="Description"
                      className={inputCls + " flex-[2]"}
                      value={cap.description}
                      onChange={(e) => updateCapability(idx, "description", e.target.value)}
                    />
                    {capabilities.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeCapability(idx)}
                        className="p-1.5 rounded-lg text-white/30 hover:text-[#EF4444] hover:bg-[#EF4444]/10 transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Tools */}
            <div>
              <label className="mb-2 block text-sm font-medium text-white/80">Tools</label>
              {toolsLoading ? (
                <p className="text-sm text-white/40">Loading tools…</p>
              ) : tools.length === 0 ? (
                <p className="text-sm text-white/40">No active tools available.</p>
              ) : (
                <div className="space-y-2">
                  {tools.map((tool) => (
                    <label
                      key={tool.id}
                      className="flex cursor-pointer items-start gap-3 rounded-xl glass px-4 py-2.5 hover:bg-white/10 transition-colors"
                    >
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-[#5B6CFF]"
                        checked={selectedTools.has(tool.id)}
                        onChange={() => toggleTool(tool.id)}
                      />
                      <div>
                        <p className="text-sm font-medium text-white/90">{tool.name}</p>
                        <p className="text-xs text-white/45">{tool.description}</p>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {generalError && (
              <p className="text-sm text-[#EF4444] bg-[#EF4444]/10 px-3 py-2 rounded-lg border border-[#EF4444]/25">
                {generalError}
              </p>
            )}

            <div className="flex gap-3">
              <BigButton type="submit" variant="gradient" size="md" loading={submitting} disabled={submitting}>
                {submitting ? "Creating…" : "Create Agent"}
              </BigButton>
              <BigButton
                type="button"
                variant="ghost"
                size="md"
                onClick={() => router.push("/agents")}
              >
                Cancel
              </BigButton>
            </div>
          </form>
        </GlassCard>
      </div>
    </div>
  )
}
