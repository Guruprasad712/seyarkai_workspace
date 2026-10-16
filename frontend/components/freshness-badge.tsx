import { cn } from "@/lib/utils"

interface FreshnessBadgeProps {
  freshness: "fresh" | "ageing" | "stale" | string
  age_days?: number
  className?: string
}

const styles = {
  fresh:  { pill: "bg-[#22C55E]/15 text-[#22C55E] border border-[#22C55E]/25", dot: "bg-[#22C55E]" },
  ageing: { pill: "bg-[#F59E0B]/15 text-[#F59E0B] border border-[#F59E0B]/25", dot: "bg-[#F59E0B]" },
  stale:  { pill: "bg-[#EF4444]/20 text-[#EF4444] border border-[#EF4444]/40 font-bold", dot: "bg-[#EF4444]" },
}

export function FreshnessBadge({ freshness, age_days, className }: FreshnessBadgeProps) {
  const s = styles[freshness as keyof typeof styles] ?? styles.stale
  const label = freshness === "stale"
    ? `STALE${age_days !== undefined ? ` · ${age_days}d` : ""}`
    : freshness === "ageing"
    ? `AGEING${age_days !== undefined ? ` · ${age_days}d` : ""}`
    : "FRESH"

  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide",
      s.pill,
      className
    )}>
      <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", s.dot)} />
      {label}
    </span>
  )
}
