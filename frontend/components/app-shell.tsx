"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { useAuth } from "@/components/auth-provider"
import { apiFetch } from "@/lib/api"
import { cn } from "@/lib/utils"
import { can } from "@/lib/permissions"

const BASE_NAV_LINKS = [
  { href: "/",          label: "Home" },
  { href: "/projects",  label: "Projects" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/agents",    label: "Agents" },
]

const ROLE_PILL_COLORS: Record<string, string> = {
  admin:    "bg-violet-500/20 text-violet-300 border-violet-500/30",
  builder:  "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
  reviewer: "bg-teal-500/20 text-teal-300 border-teal-500/30",
  observer: "bg-white/10 text-white/50 border-white/15",
}

export function AppShell() {
  const { user, logout } = useAuth()
  const pathname = usePathname()
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null)
  const [confirmLogout, setConfirmLogout] = useState(false)

  useEffect(() => {
    apiFetch<{ status: string }>("/health")
      .then(() => setBackendOnline(true))
      .catch(() => setBackendOnline(false))
  }, [])

  if (pathname === "/login") return null

  const initials = user?.name
    ? user.name.split(" ").map((n: string) => n[0]).join("").slice(0, 2).toUpperCase()
    : "?"

  const role = user?.role ?? ""
  const rolePillClass = ROLE_PILL_COLORS[role] ?? ROLE_PILL_COLORS.observer

  const navLinks = [
    ...BASE_NAV_LINKS,
    ...(user && can.manageUsers(role) ? [{ href: "/users", label: "Users" }] : []),
  ]

  return (
    <header className="sticky top-0 z-40 border-b border-white/8 bg-[rgba(7,10,20,0.85)] backdrop-blur-xl">
      <nav className="mx-auto flex max-w-7xl items-center gap-2 px-5 py-3">
        {/* Wordmark */}
        <Link
          href="/"
          className="font-heading font-bold text-lg text-white tracking-tight shrink-0 mr-4"
        >
          Seyarkai
        </Link>

        {/* Nav links */}
        <div className="flex flex-1 items-center gap-1">
          {navLinks.map(({ href, label }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "px-3.5 py-1.5 rounded-xl text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-white/12 text-white"
                    : "text-white/55 hover:text-white hover:bg-white/6"
                )}
              >
                {label}
              </Link>
            )
          })}
        </div>

        {/* Backend status dot */}
        <div className="flex items-center gap-1.5 mr-4">
          <span className={cn(
            "h-2 w-2 rounded-full shrink-0",
            backendOnline === null ? "bg-white/30" :
            backendOnline          ? "bg-[#22C55E] animate-pulse" :
                                     "bg-[#EF4444]"
          )} />
          <span className="text-xs text-white/45 hidden sm:inline">
            {backendOnline === null ? "Checking" : backendOnline ? "Backend online" : "Backend offline"}
          </span>
        </div>

        {/* User menu */}
        {user && (
          <div className="flex items-center gap-2">
            {role && (
              <span className={cn(
                "hidden sm:inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-widest border",
                rolePillClass
              )}>
                {role}
              </span>
            )}
            <button
              onClick={() => setConfirmLogout(true)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl glass text-sm text-white/70 hover:text-white hover:bg-white/10 transition-all duration-200 cursor-pointer"
            >
              <span className="flex items-center justify-center h-6 w-6 rounded-lg bg-gradient-to-br from-[#5B6CFF] to-[#C45BFF] text-white text-xs font-bold shrink-0">
                {initials}
              </span>
              <span className="hidden sm:inline">{user.name}</span>
            </button>

            {/* Logout confirmation dialog */}
            {confirmLogout && (
              <div
                className="fixed inset-0 z-50 flex items-center justify-center p-4"
                style={{ background: "rgba(7,10,20,0.75)", backdropFilter: "blur(8px)" }}
                onClick={() => setConfirmLogout(false)}
              >
                <div
                  className="glass-strong rounded-2xl px-6 py-5 w-full max-w-xs space-y-4"
                  style={{ border: "1px solid rgba(255,255,255,0.12)" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div>
                    <p className="font-heading font-semibold text-white text-base">Sign out?</p>
                    <p className="text-sm text-white/50 mt-1">You&apos;ll need to sign in again to continue.</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={logout}
                      className="flex-1 py-2 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF] hover:opacity-90 transition-opacity"
                    >
                      Sign out
                    </button>
                    <button
                      onClick={() => setConfirmLogout(false)}
                      className="flex-1 py-2 rounded-xl text-sm font-semibold text-white/70 glass hover:text-white hover:bg-white/10 transition-all border border-white/15"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </nav>
    </header>
  )
}
