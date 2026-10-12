import type { User } from "@/lib/types"

const TOKEN_KEY = "seyarkai_token"
const USER_KEY = "seyarkai_user"

function inBrowser(): boolean {
  return typeof window !== "undefined"
}

export function getToken(): string | null {
  if (!inBrowser()) return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  if (!inBrowser()) return
  localStorage.setItem(TOKEN_KEY, token)
  // Mirror to cookie so proxy.ts can read it for server-side redirects
  document.cookie = `${TOKEN_KEY}=${token}; path=/; SameSite=Lax`
}

export function clearToken(): void {
  if (!inBrowser()) return
  localStorage.removeItem(TOKEN_KEY)
  document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`
}

export function getStoredUser(): User | null {
  if (!inBrowser()) return null
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function setStoredUser(user: User): void {
  if (!inBrowser()) return
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearStoredUser(): void {
  if (!inBrowser()) return
  localStorage.removeItem(USER_KEY)
}
