import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <AppShell>
      <div className="mx-auto grid w-full max-w-4xl gap-6 py-10">
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-500">Module 0</p>
          <h1 className="text-3xl font-semibold tracking-tight">Application foundation</h1>
          <p className="max-w-2xl text-slate-600">
            The shared frontend, API, Supabase Postgres, worker, error, retry-classification,
            and logging primitives are ready for the hiring workflow modules.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Foundation boundary</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
            <p>Supabase Postgres owns durable application state.</p>
            <p>SQL migrations own schema changes.</p>
            <p>Workers never blindly repeat ambiguous side effects.</p>
            <p>Business logic begins in Module 1, not here.</p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
