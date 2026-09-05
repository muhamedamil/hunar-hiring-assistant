import { Badge } from "@/components/ui/badge";

export function CandidateContactStatus({
  hasEmail,
  hasPhone,
}: {
  hasEmail: boolean;
  hasPhone: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <Badge className={hasEmail ? "bg-emerald-100 text-emerald-800" : undefined}>
        {hasEmail ? "Email available" : "Email missing"}
      </Badge>
      <Badge className={hasPhone ? "bg-emerald-100 text-emerald-800" : undefined}>
        {hasPhone ? "Phone available" : "Phone missing"}
      </Badge>
    </div>
  );
}
