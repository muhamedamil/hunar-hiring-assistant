import { Badge } from "@/components/ui/badge";
import type { EnrichmentStatus, SourcingRunStatus } from "@/lib/sourcing/types";

export function SourcingStatusBadge({ status }: { status: SourcingRunStatus | EnrichmentStatus }) {
  return <Badge>{status.replaceAll("_", " ").toUpperCase()}</Badge>;
}
