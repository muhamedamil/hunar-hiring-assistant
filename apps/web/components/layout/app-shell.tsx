import Link from "next/link";
import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
          <Link href="/" className="font-semibold tracking-tight">
            Hunar Hiring Assistant
          </Link>
          <nav className="flex items-center gap-4 text-sm text-slate-600">
            <Link href="/jobs" className="transition-colors hover:text-slate-950">
              Jobs
            </Link>
            <Link href="/candidates" className="transition-colors hover:text-slate-950">
              Candidates
            </Link>
            <Link href="/outreach" className="transition-colors hover:text-slate-950">
              Outreach
            </Link>
          </nav>
        </div>
      </header>
      <main className="px-6">{children}</main>
    </div>
  );
}
