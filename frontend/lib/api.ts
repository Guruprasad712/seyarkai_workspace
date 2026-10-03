const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Unwraps {"detail": string | {error, failures}} per CONTRACTS.md D12
function extractDetail(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (typeof d === "object" && d !== null && "failures" in d) {
      const f = (d as { failures: unknown[] }).failures;
      return Array.isArray(f) ? f.join("; ") : String(d);
    }
    return JSON.stringify(d);
  }
  return String(body);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, extractDetail(body));
  }
  return res.json() as Promise<T>;
}
