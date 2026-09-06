import type { MatchCriterion } from "@/lib/matching/types";

const labels = {
  supported: "Supported",
  contradicted: "Contradicted",
  unknown: "Unknown",
} as const;

const styles = {
  supported: "border-emerald-200 bg-emerald-50",
  contradicted: "border-rose-200 bg-rose-50",
  unknown: "border-slate-200 bg-slate-50",
} as const;

export function MatchEvidence({ criteria }: { criteria: MatchCriterion[] }) {
  if (!criteria.length) {
    return <p className="text-sm text-slate-500">No completed evidence assessment yet.</p>;
  }
  return (
    <div className="space-y-3">
      {criteria.map((criterion) => (
        <div key={criterion.key} className={`rounded-lg border p-4 ${styles[criterion.status]}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">{criterion.label}</p>
            <span className="text-xs font-medium uppercase tracking-wide">{labels[criterion.status]}</span>
          </div>
          <p className="mt-2 text-sm text-slate-700">{criterion.reason}</p>
        </div>
      ))}
    </div>
  );
}
