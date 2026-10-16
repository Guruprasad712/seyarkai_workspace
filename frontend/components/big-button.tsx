"use client"

import { cn } from "@/lib/utils"
import { Loader2 } from "lucide-react"

interface BigButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "gradient" | "ghost" | "danger"
  size?: "sm" | "md" | "lg"
  loading?: boolean
  as?: "button"
}

const variantClasses = {
  primary:  "bg-white text-[#070A14] hover:bg-white/90 border border-white/20",
  gradient: "bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF] text-white hover:opacity-90 border-0",
  ghost:    "bg-white/8 text-white hover:bg-white/12 border border-white/15",
  danger:   "bg-gradient-to-r from-[#EF4444] to-[#DC2626] text-white hover:opacity-90 border-0",
}

const sizeClasses = {
  sm: "text-sm font-semibold px-4 py-2 rounded-xl gap-2",
  md: "text-[17px] font-bold px-6 py-3 rounded-2xl gap-2.5",
  lg: "text-lg font-bold px-8 py-4 rounded-2xl gap-3",
}

export function BigButton({
  children,
  className,
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  ...props
}: BigButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center cursor-pointer",
        "transition-all duration-200 ease-out",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5B6CFF] focus-visible:ring-offset-2 focus-visible:ring-offset-[#070A14]",
        "disabled:opacity-40 disabled:cursor-not-allowed",
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin shrink-0" />}
      {children}
    </button>
  )
}

/** Arrow tile used next to BigButton labels */
export function ArrowTile({ color = "indigo" }: { color?: "indigo" | "teal" | "pink" | "violet" }) {
  const bg: Record<string, string> = {
    indigo: "bg-[#5B6CFF]",
    teal:   "bg-[#00DCC8]",
    pink:   "bg-[#FF7AC8]",
    violet: "bg-[#C45BFF]",
  }
  return (
    <span className={cn("inline-flex items-center justify-center h-8 w-8 rounded-xl shrink-0", bg[color])}>
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M2 7h10M8 3l4 4-4 4" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </span>
  )
}
