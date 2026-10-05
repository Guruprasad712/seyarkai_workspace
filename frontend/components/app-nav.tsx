"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { LogOut } from "lucide-react"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"

const navLinks = [
  { href: "/agents", label: "Agents" },
  { href: "/projects", label: "Projects" },
  { href: "/knowledge", label: "Knowledge" },
]

export function AppNav() {
  const { user, logout } = useAuth()
  const pathname = usePathname()

  if (pathname === "/login") return null

  return (
    <header className="border-b border-border">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="font-semibold text-lg tracking-tight">
          Seyarkai
        </Link>
        <div className="flex flex-1 gap-4">
          {navLinks.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {label}
            </Link>
          ))}
        </div>
        {user && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{user.name}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="mr-1.5 h-3.5 w-3.5" />
              Logout
            </Button>
          </div>
        )}
      </nav>
    </header>
  )
}
