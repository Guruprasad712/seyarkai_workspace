"use client"

import { cn } from "@/lib/utils"

type GlowColor = "indigo" | "teal" | "pink" | "violet" | "none"

interface GlassCardProps {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  glow?: GlowColor
  padding?: boolean
  as?: "div" | "section" | "article"
}

const glowClasses: Record<GlowColor, string> = {
  indigo: "glow-indigo",
  teal:   "glow-teal",
  pink:   "glow-pink",
  violet: "glow-violet",
  none:   "",
}

export function GlassCard({
  children,
  className,
  style,
  glow = "none",
  padding = true,
  as: Tag = "div",
}: GlassCardProps) {
  return (
    <Tag
      style={style}
      className={cn(
        "glass rounded-[var(--radius-xl)]",
        "transition-[background-color,box-shadow,border-color] duration-150 ease-out",
        padding && "p-6",
        glow !== "none" && glowClasses[glow],
        className
      )}
    >
      {children}
    </Tag>
  )
}
