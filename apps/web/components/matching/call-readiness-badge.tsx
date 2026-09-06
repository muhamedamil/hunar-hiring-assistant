import { Badge } from "@/components/ui/badge";
import type { CallReadiness } from "@/lib/matching/types";

export function CallReadinessBadge({ value }: { value: CallReadiness }) {
  return (
    <Badge className={value === "ready" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-700"}>
      {value === "ready" ? "Call ready" : "No callable phone"}
    </Badge>
  );
}
