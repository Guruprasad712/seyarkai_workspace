"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { apiFetch, ApiError } from "@/lib/api"
import { getToken, setToken } from "@/lib/auth"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import type { User } from "@/lib/types"

type LoginResponse = {
  access_token: string
  token_type: string
  user: User
}

export default function LoginPage() {
  const router = useRouter()
  const { setUser } = useAuth()

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (getToken()) router.replace("/")
  }, [router])

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
      router.replace("/")
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-1 text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mb-6 text-sm text-muted-foreground">
          Seyarkai — Governed AI Execution Workspace
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30"
            />
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  )
}
