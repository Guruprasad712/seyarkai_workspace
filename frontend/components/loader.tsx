"use client"

import { motion, useReducedMotion } from "motion/react"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface LoaderStep {
  label: string
  done?: boolean
  active?: boolean
}

interface LoaderProps {
  title: string
  subtitle?: string
  steps?: LoaderStep[]
  className?: string
}

function SpinningRings() {
  const shouldReduce = useReducedMotion()

  return (
    <div className="relative flex items-center justify-center w-36 h-36">
      {/* Outer teal arc */}
      <motion.div
        className="absolute inset-0"
        animate={shouldReduce ? {} : { rotate: 360 }}
        transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
      >
        <svg viewBox="0 0 144 144" fill="none" className="w-full h-full">
          <circle
            cx="72" cy="72" r="64"
            stroke="#00DCC8"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray="260 145"
            opacity="0.85"
          />
        </svg>
      </motion.div>

      {/* Inner violet arc — counter-rotate */}
      <motion.div
        className="absolute inset-4"
        animate={shouldReduce ? {} : { rotate: -360 }}
        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
      >
        <svg viewBox="0 0 112 112" fill="none" className="w-full h-full">
          <circle
            cx="56" cy="56" r="48"
            stroke="#C45BFF"
            strokeWidth="2"
            strokeLinecap="round"
            strokeDasharray="180 120"
            opacity="0.75"
          />
        </svg>
      </motion.div>

      {/* Centre logo */}
      <div className="relative z-10 flex items-center justify-center h-12 w-12 rounded-2xl bg-gradient-to-br from-[#5B6CFF] to-[#00DCC8] shadow-lg">
        <span className="text-white font-bold text-xl font-heading">S</span>
      </div>
    </div>
  )
}

export function Loader({ title, subtitle, steps, className }: LoaderProps) {
  const doneCount = steps?.filter((s) => s.done).length ?? 0
  const total = steps?.length ?? 1
  const progress = total > 0 ? (doneCount / total) * 100 : 30

  return (
    <div className={cn(
      "fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#070A14]",
      className
    )}>
      {/* Faint radial bg glow */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 40% at 50% 40%, rgba(91,108,255,0.08) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 flex flex-col items-center gap-8 px-6 text-center max-w-md">
        <SpinningRings />

        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-white font-heading">{title}</h2>
          {subtitle && (
            <p className="text-sm text-white/55">{subtitle}</p>
          )}
        </div>

        {/* Progress bar */}
        <div className="w-full h-1 rounded-full bg-white/10 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF]"
            initial={{ width: "5%" }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>

        {/* Step list */}
        {steps && steps.length > 0 && (
          <ul className="w-full space-y-2 text-left">
            {steps.map((step, i) => (
              <li key={i} className="flex items-center gap-3">
                {step.done ? (
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[#22C55E]/20 shrink-0">
                    <Check className="h-3 w-3 text-[#22C55E]" />
                  </span>
                ) : step.active ? (
                  <span className="flex h-5 w-5 items-center justify-center shrink-0">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#C45BFF] animate-pulse" />
                  </span>
                ) : (
                  <span className="flex h-5 w-5 items-center justify-center shrink-0">
                    <span className="h-2.5 w-2.5 rounded-full border border-white/25" />
                  </span>
                )}
                <span className={cn(
                  "text-sm",
                  step.done    ? "text-white/50 line-through" :
                  step.active  ? "text-white font-semibold" :
                                 "text-white/35"
                )}>
                  {step.label}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Inline page-level spinner — not full-screen */
export function InlineLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-12 justify-center text-white/50">
      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
      </svg>
      <span className="text-sm">{label}</span>
    </div>
  )
}
