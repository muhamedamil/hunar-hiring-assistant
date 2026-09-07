import { Badge } from "@/components/ui/badge";
import { screeningStateLabels } from "@/lib/dashboard/presentation";
import type { DashboardScreeningState } from "@/lib/dashboard/types";
import { cn } from "@/lib/utils";

const classes: Record<DashboardScreeningState, string> = {
  queued: "bg-sky-100 text-sky-800",
  awaiting_result: "bg-blue-100 text-blue-800",
  dispatch_failed: "bg-rose-100 text-rose-800",
  submission_unknown: "bg-amber-100 text-amber-800",
  result_available: "bg-emerald-100 text-emerald-800",
  result_unavailable: "bg-slate-200 text-slate-700",
  result_invalid: "bg-rose-100 text-rose-800",
};

export function ScreeningStateBadge({ state, className }: { state: DashboardScreeningState; className?: string }) {
  return <Badge className={cn(classes[state], className)}>{screeningStateLabels[state]}</Badge>;
}
