"use client"

import { useEffect, useState } from "react"
import { apiFetch, ApiError } from "@/lib/api"
import { getToken, setToken } from "@/lib/auth"
import { useAuth } from "@/components/auth-provider"
import { BigButton } from "@/components/big-button"
import { DEMO_ACCOUNTS, type DemoAccount } from "@/lib/demo-accounts"
import type { User } from "@/lib/types"

type LoginResponse = {
  access_token: string
  token_type: string
  user: User
}

const SHOW_DEMO = process.env.NEXT_PUBLIC_SHOW_DEMO_ACCESS !== "false"

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text).catch(() => {})
    setDone(true)
    setTimeout(() => setDone(false), 2000)
  }
  return (
    <button
      type="button"
      onClick={copy}
      title={`Copy ${label}`}
      className="shrink-0 text-[10px] font-mono text-white/35 hover:text-white/70 transition-colors px-1.5 py-0.5 rounded border border-white/10 hover:border-white/25"
    >
      {done ? "✓" : "copy"}
    </button>
  )
}

function DemoCard({
  onFill,
  selected,
}: {
  onFill: (acct: DemoAccount) => void
  selected: string | null
}) {
  return (
    <aside className="glass rounded-2xl px-5 py-5 space-y-4 border border-[#5B6CFF]/20"
      style={{ boxShadow: "0 0 20px rgba(91,108,255,0.08)" }}
    >
      <div>
        <p className="font-heading font-semibold text-white text-sm">Try the demo</p>
        <p className="text-[11px] text-white/45 mt-0.5 leading-snug">
          Pick a role. Open two windows to see the team work live.
        </p>
      </div>

      <div className="space-y-3">
        {DEMO_ACCOUNTS.map((acct) => {
          const isSelected = selected === acct.role
          return (
            <div key={acct.role} className="space-y-1.5">
              {/* Role chip — click to fill form */}
              <button
                type="button"
                onClick={() => onFill(acct)}
                className={`w-full text-left px-3 py-2 rounded-xl border transition-all ${
                  isSelected
                    ? "border-[#5B6CFF]/60 bg-[#5B6CFF]/12 ring-1 ring-[#5B6CFF]/40"
                    : "border-white/10 bg-white/4 hover:bg-white/8 hover:border-white/20"
                }`}
              >
                <span className="inline-flex items-center gap-2">
                  <span
                    className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide text-white"
                    style={{
                      background: "linear-gradient(to right, #5B6CFF, #C45BFF)",
                    }}
                  >
                    {acct.role}
                  </span>
                  <span className="text-[11px] text-white/50">{acct.meaning}</span>
                </span>
              </button>

              {/* Credential rows — email + password with copy buttons */}
              {isSelected && (
                <div className="pl-3 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/30 w-10 shrink-0">email</span>
                    <span className="text-[11px] text-white/70 font-mono truncate flex-1">{acct.email}</span>
                    <CopyButton text={acct.email} label="email" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/30 w-10 shrink-0">pass</span>
                    <span className="text-[11px] text-white/70 font-mono flex-1">{"•".repeat(Math.min(acct.password.length, 12))}</span>
                    <CopyButton text={acct.password} label="password" />
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}

export default function LoginPage() {
  const { setUser } = useAuth()

  const [email, setEmail]             = useState("")
  const [password, setPassword]       = useState("")
  const [error, setError]             = useState("")
  const [loading, setLoading]         = useState(false)
  const [selectedDemo, setSelectedDemo] = useState<string | null>(null)
  const [demoOpen, setDemoOpen]       = useState(false)

  useEffect(() => {
    if (getToken()) window.location.href = "/"
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      })
      setToken(data.access_token)
      setUser(data.user)
      window.location.href = "/"
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed")
    } finally {
      setLoading(false)
    }
  }

  function fillDemo(acct: DemoAccount) {
    setEmail(acct.email)
    setPassword(acct.password)
    setSelectedDemo(acct.role)
  }

  return (
    <div className="flex min-h-screen bg-[#070A14]">
      {/* Faint radial glow */}
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden"
        aria-hidden
      >
        <div
          style={{
            position: "absolute",
            top: "-10%",
            right: "-5%",
            width: "50%",
            height: "60%",
            background: "radial-gradient(ellipse, rgba(91,108,255,0.12) 0%, transparent 70%)",
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: "-10%",
            right: "10%",
            width: "40%",
            height: "50%",
            background: "radial-gradient(ellipse, rgba(196,91,255,0.10) 0%, transparent 70%)",
          }}
        />
      </div>

      {/* LEFT — brand / pitch panel */}
      <div className="relative hidden md:flex md:w-[45%] flex-col justify-between p-10 overflow-hidden"
        style={{
          background: "linear-gradient(160deg, rgba(91,108,255,0.25) 0%, rgba(7,10,20,0.95) 60%)",
          borderRight: "1px solid rgba(255,255,255,0.08)",
        }}
      >
        {/* Wordmark */}
        <span className="font-heading font-bold text-xl text-white tracking-tight">Seyarkai</span>

        {/* Main pitch */}
        <div className="space-y-5">
          <h1 className="font-heading text-5xl font-extrabold text-white leading-tight">
            Co-op mode for AI work.
          </h1>
          <p className="text-white/60 text-base leading-relaxed max-w-xs">
            Your team and your agents, on the same task, live. Humans approve every checkpoint.
          </p>

          {/* Feature chips */}
          <div className="flex flex-wrap gap-2 pt-2">
            {["Watch", "Steer", "Approve"].map((f) => (
              <span
                key={f}
                className="px-3 py-1.5 rounded-full text-sm text-white/70 glass"
              >
                {f}
              </span>
            ))}
          </div>
        </div>

        {/* Tamil script — subtle brand watermark */}
        <div className="font-tamil text-6xl font-black opacity-10 text-white select-none">
          செயற்கை
        </div>
      </div>

      {/* RIGHT — form + demo card */}
      <div className="flex flex-1 items-start justify-center px-6 py-12 overflow-y-auto">
        <div className="w-full max-w-sm space-y-6">
          {/* Mobile wordmark */}
          <div className="md:hidden">
            <span className="font-heading font-bold text-xl text-white">Seyarkai</span>
          </div>

          <div>
            <h2 className="font-heading text-3xl font-bold text-white">Welcome back</h2>
            <p className="mt-1.5 text-white/50 text-sm">Sign in to your workspace</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="email" className="text-sm font-medium text-white/80">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-12 rounded-xl glass px-4 text-white text-sm placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 transition-all"
                placeholder="admin@seyarkai.example"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="text-sm font-medium text-white/80">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-12 rounded-xl glass px-4 text-white text-sm placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-[#5B6CFF]/60 transition-all"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-sm text-[#EF4444] bg-[#EF4444]/10 px-3 py-2 rounded-lg border border-[#EF4444]/25">
                {error}
              </p>
            )}

            <BigButton
              type="submit"
              variant="gradient"
              size="lg"
              className="w-full"
              loading={loading}
            >
              {loading ? "Signing in…" : "Sign in"}
            </BigButton>
          </form>

          {/* Demo access — desktop always visible, narrow behind toggle */}
          {SHOW_DEMO && (
            <>
              {/* Narrow-screen toggle */}
              <div className="md:hidden text-center">
                <button
                  type="button"
                  onClick={() => setDemoOpen((o) => !o)}
                  className="text-xs text-white/40 hover:text-white/70 underline transition-colors"
                >
                  {demoOpen ? "Hide demo access" : "Demo access"}
                </button>
              </div>

              {/* Card: always on md+, toggled on small */}
              <div className={demoOpen ? "block" : "hidden md:block"}>
                <DemoCard onFill={fillDemo} selected={selectedDemo} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
