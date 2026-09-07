"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { ScreeningStateBadge } from "@/components/dashboard/screening-state-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listOutreachRequests } from "@/lib/outreach/api";
import { outreachKeys } from "@/lib/outreach/queries";

const PAGE_SIZE = 20;

export function OutreachList() {
  const [offset, setOffset] = useState(0);
  const listQuery = useQuery({
    queryKey: outreachKeys.list(offset),
    queryFn: () => listOutreachRequests(PAGE_SIZE, offset),
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Outreach</h1>
        <p className="mt-2 text-sm text-slate-600">Voice screening outreach and its current execution or result state.</p>
      </div>
      <Card>
        <CardHeader><CardTitle>Outreach requests</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {listQuery.isLoading ? <p className="text-sm text-slate-500">Loading outreach…</p> : null}
          {listQuery.isError ? <p role="alert" className="text-sm text-rose-700">Unable to load outreach requests.</p> : null}
          {listQuery.data?.items.length === 0 ? <p className="text-sm text-slate-500">No outreach requests yet.</p> : null}
          {listQuery.data?.items.map((request) => (
            <Link key={request.id} href={`/outreach/${request.id}`} className="block rounded-lg border p-4 transition-shadow hover:shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{request.candidate_name}</p>
                  <p className="mt-1 text-sm text-slate-700">{request.job_title}</p>
                  <p className="mt-1 text-xs text-slate-500">Job version v{request.job_definition_version} · {request.screening_questions.length} questions</p>
                </div>
                {request.screening_state ? <ScreeningStateBadge state={request.screening_state} /> : request.readiness === "READY_FOR_EXECUTION" ? <Badge className="bg-emerald-100 text-emerald-800">Ready for execution</Badge> : <Badge className="bg-amber-100 text-amber-800">Outreach context changed</Badge>}
              </div>
            </Link>
          ))}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" disabled={offset === 0 || listQuery.isFetching} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>Previous</Button>
            <Button variant="outline" size="sm" disabled={listQuery.isFetching || (listQuery.data?.items.length ?? 0) < PAGE_SIZE} onClick={() => setOffset((value) => value + PAGE_SIZE)}>Next</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
