import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl space-y-6 py-10">
        <div className="space-y-2">
          <p className="text-sm font-medium text-slate-500">Modules 1 + 2</p>
          <h1 className="text-3xl font-semibold tracking-tight">Hiring definition & Candidate Core</h1>
          <p className="max-w-2xl text-slate-600">
            Maintain approved hiring definitions and one global Candidate identity that both
            assessment streams can reuse safely.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Jobs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-600">
              <p>
                AI analysis remains optional. Only recruiter-approved READY snapshots become
                downstream hiring truth.
              </p>
              <Button asChild>
                <Link href="/jobs">Open jobs</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Candidates</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-600">
              <p>
                Manual and future provider-sourced people converge on one revision-safe Candidate
                profile with separate provider identities.
              </p>
              <Button asChild>
                <Link href="/candidates">Open candidates</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
