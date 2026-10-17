"use client"

import { useEffect, useState } from "react"

export function ForbiddenToast() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    function handler(e: Event) {
      const detail = (e as CustomEvent<string>).detail
      setMessage(detail || "You don't have permission to do that.")
      const timer = setTimeout(() => setMessage(null), 4000)
      return () => clearTimeout(timer)
    }
    window.addEventListener("api-forbidden", handler)
    return () => window.removeEventListener("api-forbidden", handler)
  }, [])

  if (!message) return null

  return (
    <div
      role="alert"
      className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-2xl border border-[#EF4444]/30 bg-[#0D0F1A]/90 px-5 py-3.5 shadow-[0_0_32px_rgba(239,68,68,0.2)] backdrop-blur-xl"
    >
      <span className="h-2 w-2 rounded-full bg-[#EF4444] shrink-0" />
      <p className="text-sm text-white/85">{message}</p>
      <button
        onClick={() => setMessage(null)}
        className="ml-2 text-white/35 hover:text-white transition-colors text-xs"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}
