import { Suspense } from "react";

import { ScreeningsWorkspace } from "@/components/dashboard/screenings-workspace";
import { AppShell } from "@/components/layout/app-shell";

export default function ScreeningsPage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-6xl py-10">
        <Suspense fallback={<p className="text-sm text-slate-500">Loading screenings…</p>}>
          <ScreeningsWorkspace />
        </Suspense>
      </div>
    </AppShell>
  );
}
