"use client"

import { useEffect, useState } from "react"
import { apiFetch, ApiError } from "@/lib/api"
import { GlassCard } from "@/components/glass-card"
import { BigButton } from "@/components/big-button"
import { StatusPill } from "@/components/status-pill"
import { InlineLoader } from "@/components/loader"
import { useAuth } from "@/components/auth-provider"
import { can } from "@/lib/permissions"
import Link from "next/link"
import { cn } from "@/lib/utils"

const inputCls =
  "w-full rounded-xl glass px-4 py-3 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50 transition-all"

const selectCls =
  "rounded-xl glass px-3 py-2 text-sm text-white bg-[rgba(7,10,20,0.7)] outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 disabled:opacity-50"

const VALID_ROLES = ["admin", "builder", "reviewer", "observer"] as const
type Role = typeof VALID_ROLES[number]

const ROLE_PILL: Record<Role, string> = {
  admin:    "bg-violet-500/20 text-violet-300 border border-violet-500/30",
  builder:  "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30",
  reviewer: "bg-teal-500/20 text-teal-300 border border-teal-500/30",
  observer: "bg-white/10 text-white/50 border border-white/15",
}

type UserAdminOut = {
  id: string
  email: string
  name: string
  role: Role
  status: string
  created_at: string
}

// ─── Add User Dialog ──────────────────────────────────────────────────────────

function AddUserDialog({ onAdded, onClose }: { onAdded: (u: UserAdminOut) => void; onClose: () => void }) {
  const [name, setName]         = useState("")
  const [email, setEmail]       = useState("")
  const [password, setPassword] = useState("")
  const [role, setRole]         = useState<Role>("observer")
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState("")

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setSaving(true)
    try {
      const u = await apiFetch<UserAdminOut>("/users", {
        method: "POST",
        body: JSON.stringify({ name, email, temp_password: password, role }),
      })
      onAdded(u)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <GlassCard className="w-full max-w-md mx-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <h2 className="font-heading text-xl font-bold text-white">Add User</h2>
          {error && <p className="text-xs text-[#EF4444]">{error}</p>}

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">Name</label>
            <input className={inputCls} required value={name} onChange={e => setName(e.target.value)} placeholder="Full name" />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">Email</label>
            <input className={inputCls} type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="user@example.com" />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">Temporary password</label>
            <input className={inputCls} type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Min 8 characters" />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-white/80">Role</label>
            <select className={inputCls} value={role} onChange={e => setRole(e.target.value as Role)}>
              {VALID_ROLES.map(r => <option key={r} value={r} className="bg-[#0D1425]">{r}</option>)}
            </select>
          </div>

          <div className="flex gap-2 pt-1">
            <BigButton type="submit" variant="gradient" size="md" loading={saving}>Add User</BigButton>
            <BigButton type="button" variant="ghost" size="md" onClick={onClose}>Cancel</BigButton>
          </div>
        </form>
      </GlassCard>
    </div>
  )
}

// ─── User Row ─────────────────────────────────────────────────────────────────

function UserRow({ user: u, currentUserId, onUpdate }: {
  user: UserAdminOut
  currentUserId: string
  onUpdate: (updated: UserAdminOut) => void
}) {
  const [editRole, setEditRole] = useState<Role>(u.role)
  const [savingRole, setSavingRole] = useState(false)
  const [savingStatus, setSavingStatus] = useState(false)
  const [error, setError] = useState("")

  async function handleSaveRole() {
    if (editRole === u.role) return
    setError("")
    setSavingRole(true)
    try {
      const updated = await apiFetch<UserAdminOut>(`/users/${u.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: editRole }),
      })
      onUpdate(updated)
    } catch (err) {
      setEditRole(u.role)
      setError(err instanceof ApiError ? err.message : "Failed to update role")
    } finally {
      setSavingRole(false)
    }
  }

  async function handleToggleStatus() {
    setError("")
    setSavingStatus(true)
    const endpoint = u.status === "active" ? `/users/${u.id}/deactivate` : `/users/${u.id}/activate`
    try {
      const updated = await apiFetch<UserAdminOut>(endpoint, { method: "PATCH" })
      onUpdate(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update status")
    } finally {
      setSavingStatus(false)
    }
  }

  const isSelf = u.id === currentUserId

  return (
    <tr className="border-b border-white/6 last:border-0">
      <td className="px-4 py-3">
        <p className="text-sm font-medium text-white">{u.name}</p>
        <p className="text-xs text-white/40 font-mono">{u.email}</p>
      </td>
      <td className="px-4 py-3">
        <span className={cn(
          "inline-flex items-center px-2.5 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wide",
          ROLE_PILL[u.role] ?? ROLE_PILL.observer
        )}>
          {u.role}
        </span>
      </td>
      <td className="px-4 py-3">
        <StatusPill status={u.status} />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <select
            className={selectCls}
            value={editRole}
            onChange={e => setEditRole(e.target.value as Role)}
            disabled={savingRole}
          >
            {VALID_ROLES.map(r => <option key={r} value={r} className="bg-[#0D1425]">{r}</option>)}
          </select>
          {editRole !== u.role && (
            <BigButton variant="ghost" size="sm" loading={savingRole} onClick={handleSaveRole}>
              Save
            </BigButton>
          )}
          <BigButton
            variant="ghost"
            size="sm"
            loading={savingStatus}
            onClick={handleToggleStatus}
            disabled={isSelf && u.status === "active"}
          >
            {u.status === "active" ? "Deactivate" : "Activate"}
          </BigButton>
        </div>
        {error && <p className="text-xs text-[#EF4444] mt-1">{error}</p>}
      </td>
    </tr>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const [users, setUsers]     = useState<UserAdminOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState("")
  const [showAdd, setShowAdd] = useState(false)

  useEffect(() => {
    if (!currentUser) return
    if (!can.manageUsers(currentUser.role)) {
      setLoading(false)
      return
    }
    apiFetch<UserAdminOut[]>("/users")
      .then(setUsers)
      .catch(err => setError(err instanceof ApiError ? err.message : "Failed to load users"))
      .finally(() => setLoading(false))
  }, [currentUser])

  if (!currentUser || (!loading && !can.manageUsers(currentUser.role))) {
    return (
      <div className="min-h-screen bg-[#070A14] flex items-center justify-center">
        <GlassCard className="max-w-sm w-full text-center py-10">
          <p className="text-white/60 mb-4">You don&apos;t have permission to manage users.</p>
          <Link href="/"><BigButton variant="ghost" size="md">Back to Home</BigButton></Link>
        </GlassCard>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#070A14]">
      <div className="mx-auto max-w-5xl px-4 py-10">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-heading text-4xl font-black text-white">User Management</h1>
            <p className="mt-1.5 text-white/50">Manage roles and access for workspace members.</p>
          </div>
          <BigButton variant="gradient" size="md" onClick={() => setShowAdd(true)}>
            + Add User
          </BigButton>
        </div>

        {showAdd && (
          <AddUserDialog
            onAdded={(u) => { setUsers(prev => [u, ...prev]); setShowAdd(false) }}
            onClose={() => setShowAdd(false)}
          />
        )}

        {loading && <InlineLoader label="Loading users…" />}

        {error && (
          <div className="rounded-xl bg-[#EF4444]/10 border border-[#EF4444]/25 px-4 py-3 text-sm text-[#EF4444]">
            {error}
          </div>
        )}

        {!loading && !error && (
          <GlassCard padding={false}>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-white/8">
                  <th className="px-4 py-3 text-xs font-semibold text-white/40 uppercase tracking-wider">User</th>
                  <th className="px-4 py-3 text-xs font-semibold text-white/40 uppercase tracking-wider">Role</th>
                  <th className="px-4 py-3 text-xs font-semibold text-white/40 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-xs font-semibold text-white/40 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-10 text-center text-sm text-white/35">No users found.</td>
                  </tr>
                ) : (
                  users.map(u => (
                    <UserRow
                      key={u.id}
                      user={u}
                      currentUserId={currentUser.id}
                      onUpdate={(updated) => setUsers(prev => prev.map(x => x.id === updated.id ? updated : x))}
                    />
                  ))
                )}
              </tbody>
            </table>
          </GlassCard>
        )}
      </div>
    </div>
  )
}
