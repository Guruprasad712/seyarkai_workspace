import { getToken, clearToken } from "@/lib/auth"
import type { PublishFailure } from "@/lib/types"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message)
  }
}

// Unwraps {"detail": string | {error, failures}} per CONTRACTS.md D12
function extractDetail(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === "string") return d
    if (typeof d === "object" && d !== null && "failures" in d) {
      const f = (d as { failures: unknown[] }).failures
      if (Array.isArray(f)) {
        return f
          .map((item) =>
            typeof item === "object" && item !== null && "message" in item
              ? (item as { message: string }).message
              : String(item),
          )
          .join("; ")
      }
      return String(d)
    }
    return JSON.stringify(d)
  }
  return String(body)
}

// Returns the failures array from a publish validation error body, or null
export function extractPublishFailures(body: unknown): PublishFailure[] | null {
  if (typeof body !== "object" || body === null) return null
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail !== "object" || detail === null) return null
  const failures = (detail as { failures?: unknown }).failures
  if (!Array.isArray(failures)) return null
  return failures as PublishFailure[]
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (token) headers["Authorization"] = `Bearer ${token}`

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))

    if (res.status === 401) {
      clearToken()
      if (typeof window !== "undefined") {
        window.location.href = "/login"
      }
    }

    throw new ApiError(res.status, extractDetail(body), body)
  }

  return res.json() as Promise<T>
}
