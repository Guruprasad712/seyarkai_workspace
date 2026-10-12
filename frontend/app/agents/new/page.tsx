"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { Plus, Trash2 } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { Button } from "@/components/ui/button"
import type { Agent, Capability, McpTool } from "@/lib/types"

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-50"

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
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">New Agent</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Create an agent and its first draft version.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Name */}
        <Field label="Name" error={fieldErrors.name}>
          <input
            className={inputCls}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>

        {/* Description */}
        <Field label="Description">
          <textarea
            className={inputCls + " min-h-[72px] resize-y"}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>

        {/* Role / Purpose */}
        <Field label="Role / Purpose">
          <input
            className={inputCls}
            value={rolePurpose}
            onChange={(e) => setRolePurpose(e.target.value)}
          />
        </Field>

        {/* Instructions */}
        <Field label="Instructions (version 1.0)">
          <textarea
            className={inputCls + " min-h-[120px] resize-y font-mono text-xs"}
            required
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </Field>

        {/* Capabilities */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="text-sm font-medium">Capabilities</label>
            <Button type="button" variant="ghost" size="xs" onClick={addCapability}>
              <Plus className="mr-1 h-3 w-3" />
              Add
            </Button>
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
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeCapability(idx)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Tools */}
        <div>
          <label className="mb-2 block text-sm font-medium">Tools</label>
          {toolsLoading ? (
            <p className="text-sm text-muted-foreground">Loading tools…</p>
          ) : tools.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active tools available.</p>
          ) : (
            <div className="space-y-2">
              {tools.map((tool) => (
                <label
                  key={tool.id}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border border-border px-3 py-2.5 hover:bg-muted/40"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={selectedTools.has(tool.id)}
                    onChange={() => toggleTool(tool.id)}
                  />
                  <div>
                    <p className="text-sm font-medium">{tool.name}</p>
                    <p className="text-xs text-muted-foreground">{tool.description}</p>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        {generalError && (
          <p className="text-sm text-destructive">{generalError}</p>
        )}

        <div className="flex gap-3">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create Agent"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/agents")}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  )
}

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
    <div className="space-y-1">
      <label className="text-sm font-medium">{label}</label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
