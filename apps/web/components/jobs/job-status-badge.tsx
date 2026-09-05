import { Badge } from "@/components/ui/badge";
import type { JobStatus } from "@/lib/jobs/types";

export function JobStatusBadge({ status, version }: { status: JobStatus; version: number | null }) {
  return (
    <Badge className={status === "ready" ? "bg-emerald-50 text-emerald-700" : undefined}>
      {status === "ready" ? `Ready${version ? ` · v${version}` : ""}` : "Draft"}
    </Badge>
  );
}
