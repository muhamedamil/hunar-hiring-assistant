import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b bg-white">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center px-6">
          <div className="font-semibold tracking-tight">Hunar Hiring Assistant</div>
        </div>
      </header>
      <main className="px-6">{children}</main>
    </div>
  );
}
