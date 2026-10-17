import type { Metadata } from "next"
import { Sora, DM_Sans, JetBrains_Mono, Noto_Sans_Tamil } from "next/font/google"
import { AuthProvider } from "@/components/auth-provider"
import { AppShell } from "@/components/app-shell"
import { ForbiddenToast } from "@/components/forbidden-toast"
import "./globals.css"

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
  weight: ["400", "600", "700", "800"],
})

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
})

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jb-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
})

const notoSansTamil = Noto_Sans_Tamil({
  variable: "--font-noto-tamil",
  subsets: ["tamil"],
  weight: ["400", "700", "900"],
})

export const metadata: Metadata = {
  title: "Seyarkai",
  description: "Governed AI Execution Workspace",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${sora.variable} ${dmSans.variable} ${jetbrainsMono.variable} ${notoSansTamil.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <AuthProvider>
          <AppShell />
          <ForbiddenToast />
          <main className="flex-1">{children}</main>
        </AuthProvider>
      </body>
    </html>
  )
}
