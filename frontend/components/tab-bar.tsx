"use client"

import { cn } from "@/lib/utils"

export interface Tab {
  id: string
  label: string
  dot?: boolean
  dotColor?: string
}

interface TabBarProps {
  tabs: Tab[]
  activeTab: string
  onTabChange: (id: string) => void
  className?: string
}

export function TabBar({ tabs, activeTab, onTabChange, className }: TabBarProps) {
  return (
    <div className={cn("flex items-center gap-1 p-1 glass rounded-2xl", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "relative flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-sm font-medium transition-all duration-200 ease-out cursor-pointer",
            activeTab === tab.id
              ? "bg-gradient-to-r from-[#5B6CFF] to-[#C45BFF] text-white shadow-lg"
              : "text-white/60 hover:text-white hover:bg-white/8"
          )}
        >
          {tab.label}
          {tab.dot && (
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full shrink-0",
                tab.dotColor ?? "bg-[#FF7AC8]",
                activeTab !== tab.id && "animate-pulse"
              )}
            />
          )}
        </button>
      ))}
    </div>
  )
}
