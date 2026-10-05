"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react"
import { useRouter } from "next/navigation"
import {
  clearStoredUser,
  clearToken,
  getStoredUser,
  setStoredUser,
} from "@/lib/auth"
import type { User } from "@/lib/types"

type AuthContextValue = {
  user: User | null
  setUser: (user: User) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [user, setUserState] = useState<User | null>(null)

  useEffect(() => {
    setUserState(getStoredUser())
  }, [])

  const setUser = useCallback((u: User) => {
    setStoredUser(u)
    setUserState(u)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    clearStoredUser()
    setUserState(null)
    router.push("/login")
  }, [router])

  return (
    <AuthContext.Provider value={{ user, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}
