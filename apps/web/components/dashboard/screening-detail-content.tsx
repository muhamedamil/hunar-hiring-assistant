import { ScreeningStateBadge } from "@/components/dashboard/screening-state-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { answerDisplay, humanize, submissionStatusLabels } from "@/lib/dashboard/presentation";
import type { DashboardScreeningDetail } from "@/lib/dashboard/types";

export function ScreeningDetailContent({
  detail,
  showIdentity = true,
}: {
  detail: DashboardScreeningDetail;
  showIdentity?: boolean;
}) {
  const humanUnavailable = detail.answered_by === "MACHINE" || detail.answered_by === "UNKNOWN";

  return (
    <div className="space-y-6">
      {showIdentity ? (
        <Card>
          <CardHeader>
            <CardTitle>Candidate &amp; Role</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 text-sm md:grid-cols-2">
            <div>
              <p className="text-slate-500">Candidate</p>
              <p className="font-medium">{detail.candidate_name}</p>
            </div>
            <div>
              <p className="text-slate-500">Role</p>
              <p className="font-medium">{detail.job_title}</p>
            </div>
            <div>
              <p className="text-slate-500">Historical Job version</p>
              <p className="font-medium">v{detail.job_definition_version}</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Call Status</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm md:grid-cols-2 lg:grid-cols-3">
          <div>
            <p className="text-slate-500">Submission status</p>
            <p className="font-medium">{submissionStatusLabels[detail.submission_status]}</p>
          </div>
          <div>
            <p className="text-slate-500">Screening/result state</p>
            <div className="mt-1">
              <ScreeningStateBadge state={detail.screening_state} />
            </div>
          </div>
          <div>
            <p className="text-slate-500">Lifecycle</p>
            <p className="font-medium">{humanize(detail.lifecycle_status)}</p>
          </div>
          <div>
            <p className="text-slate-500">Outcome</p>
            <p className="font-medium">{humanize(detail.conversation_outcome)}</p>
          </div>
          <div>
            <p className="text-slate-500">Interest</p>
            <p className="font-medium">{humanize(detail.candidate_interest)}</p>
          </div>
          <div>
            <p className="text-slate-500">Duration</p>
            <p className="font-medium">
              {detail.duration_seconds === null ? "—" : `${Math.round(detail.duration_seconds)} sec`}
            </p>
          </div>
          <div>
            <p className="text-slate-500">Answered by</p>
            <p className="font-medium">{humanize(detail.answered_by)}</p>
          </div>
          <div>
            <p className="text-slate-500">Recording available</p>
            <p className="font-medium">{detail.recording_available ? "Yes" : "No"}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Screening Responses</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {detail.screening_state === "result_invalid" ? (
            <p className="rounded-md bg-rose-50 p-3 text-rose-800">
              Screening result could not be safely normalized.
            </p>
          ) : null}
          {humanUnavailable ? (
            <p className="rounded-md bg-amber-50 p-3 text-amber-800">
              No human screening answers are available for this call.
            </p>
          ) : null}
          {detail.questions.length === 0 ? (
            <p className="text-slate-500">No frozen screening questions are available.</p>
          ) : (
            <ol className="space-y-4">
              {detail.questions.map((question) => (
                <li key={question.question_id} className="rounded-lg border p-4">
                  <p className="font-medium">
                    <span aria-hidden="true">{question.position}. </span>
                    <span>{question.prompt}</span>
                  </p>
                  <p className="mt-2 text-slate-700">
                    {answerDisplay(question.answer_state, question.answer_text)}
                  </p>
                </li>
              ))}
            </ol>
          )}
          {detail.notes ? (
            <div>
              <p className="font-medium">Notes</p>
              <p className="mt-1 text-slate-700">{detail.notes}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
