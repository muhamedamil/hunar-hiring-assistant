import Link from "next/link";
import type { ReactNode } from "react";

const links = [
  ["Dashboard", "/"],
  ["Jobs", "/jobs"],
  ["Candidates", "/candidates"],
  ["Outreach", "/outreach"],
  ["Screenings", "/screenings"],
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <Link href="/" className="font-semibold tracking-tight">Hunar Hiring Assistant</Link>
          <nav className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
            {links.map(([label, href]) => <Link key={href} href={href} className="transition-colors hover:text-slate-950">{label}</Link>)}
          </nav>
        </div>
      </header>
      <main className="px-6">{children}</main>
    </div>
  );
}
