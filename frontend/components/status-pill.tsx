import { cn } from "@/lib/utils"

const pillStyles: Record<string, string> = {
  queued:               "bg-white/10 text-white/70",
  running:              "bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/30",
  waiting_for_approval: "bg-[#FF7AC8]/20 text-[#FF7AC8] border border-[#FF7AC8]/30",
  completed:            "bg-[#22C55E]/20 text-[#22C55E] border border-[#22C55E]/30",
  failed:               "bg-[#EF4444]/20 text-[#EF4444] border border-[#EF4444]/30",
  active:               "bg-[#22C55E]/20 text-[#22C55E] border border-[#22C55E]/30",
  in_progress:          "bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]/30",
  new:                  "bg-[#5B6CFF]/20 text-[#5B6CFF] border border-[#5B6CFF]/30",
  published:            "bg-[#5B6CFF]/20 text-[#5B6CFF] border border-[#5B6CFF]/30",
  draft:                "bg-white/10 text-white/60",
  pending:              "bg-[#FF7AC8]/20 text-[#FF7AC8] border border-[#FF7AC8]/30",
  approved:             "bg-[#22C55E]/20 text-[#22C55E] border border-[#22C55E]/30",
  rejected:             "bg-[#EF4444]/20 text-[#EF4444] border border-[#EF4444]/30",
  upcoming:             "bg-white/8 text-white/40",
}

const dotColor: Record<string, string> = {
  running:              "bg-[#F59E0B]",
  waiting_for_approval: "bg-[#FF7AC8]",
  completed:            "bg-[#22C55E]",
  failed:               "bg-[#EF4444]",
  active:               "bg-[#22C55E]",
  pending:              "bg-[#FF7AC8]",
  approved:             "bg-[#22C55E]",
  rejected:             "bg-[#EF4444]",
}

const friendlyLabel: Record<string, string> = {
  waiting_for_approval: "Waiting for you",
  in_progress:          "In progress",
}

interface StatusPillProps {
  status: string
  dot?: boolean
  className?: string
}

export function StatusPill({ status, dot = false, className }: StatusPillProps) {
  const cls = pillStyles[status] ?? "bg-white/10 text-white/60"
  const label = friendlyLabel[status] ?? status.replace(/_/g, " ")
  const dc = dotColor[status]

  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
      cls,
      className
    )}>
      {dot && dc && (
        <span className={cn("inline-block h-1.5 w-1.5 rounded-full shrink-0 animate-pulse", dc)} />
      )}
      {label}
    </span>
  )
}
