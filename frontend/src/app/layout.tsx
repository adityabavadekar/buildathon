import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FORTX - Flow Orchestration & Revenue Trust eXecution',
  description: 'FORTX revenue recovery agent dashboard',
  icons: {
    icon: '/favicon.svg',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      {/* Body attributes are extended by browser extensions (for example the
      VS Code extension adds vsc-initialized); suppress hydration mismatch
      warnings for that known third-party injection. */}
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}
