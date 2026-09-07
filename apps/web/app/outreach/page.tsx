import { AppShell } from "@/components/layout/app-shell";
import { OutreachList } from "@/components/outreach/outreach-list";

export default function OutreachPage() {
  return (
    <AppShell>
      <div className="mx-auto w-full max-w-5xl py-10">
        <OutreachList />
      </div>
    </AppShell>
  );
}
