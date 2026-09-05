import { CandidateEditor } from "@/components/candidates/candidate-editor";
import { AppShell } from "@/components/layout/app-shell";

export default function NewCandidatePage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <CandidateEditor />
      </div>
    </AppShell>
  );
}
