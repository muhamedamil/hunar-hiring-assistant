import { AppShell } from "@/components/layout/app-shell";
import { JobEditor } from "@/components/jobs/job-editor";

export default function NewJobPage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <JobEditor />
      </div>
    </AppShell>
  );
}
