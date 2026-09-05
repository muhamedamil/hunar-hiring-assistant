import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <AppShell>
      <div className="mx-auto grid w-full max-w-4xl gap-6 py-10">
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-500">Module 1</p>
          <h1 className="text-3xl font-semibold tracking-tight">Job & screening definition</h1>
          <p className="max-w-2xl text-slate-600">
            Build one recruiter-approved hiring definition that becomes the shared source of truth for
            people sourcing and Hunar voice screening.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Hiring-definition workflow</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-slate-600">
            <p>
              AI analysis is optional and produces editable suggestions only. A recruiter-approved READY
              version is stored as an immutable definition snapshot.
            </p>
            <Button asChild>
              <Link href="/jobs">Open jobs</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
