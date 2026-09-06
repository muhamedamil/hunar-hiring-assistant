import { Badge } from "@/components/ui/badge";
import type { MatchEvaluation } from "@/lib/matching/types";

export function MatchScore({ match }: { match: MatchEvaluation | null }) {
  if (!match || match.match_score === null || match.evidence_coverage === null) {
    return <Badge>Not analyzed</Badge>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <Badge>Match {match.match_score}%</Badge>
      <Badge>Coverage {match.evidence_coverage}%</Badge>
    </div>
  );
}
