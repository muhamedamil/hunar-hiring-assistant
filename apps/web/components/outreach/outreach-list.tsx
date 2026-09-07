"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

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
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-medium text-slate-500">Module 5</p>
        <h1 className="text-3xl font-semibold tracking-tight">Outreach</h1>
        <p className="mt-2 text-sm text-slate-600">Immutable voice-screening contexts ready for future execution.</p>
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
                  {request.candidate_location ? (
                    <p className="text-sm text-slate-600">{request.candidate_location}</p>
                  ) : null}
                  <p className="mt-1 text-sm text-slate-500">
                    {request.requested_action} · {request.masked_phone} · {request.screening_questions.length} questions
                  </p>
                </div>
                <span className={request.readiness === "READY_FOR_EXECUTION" ? "text-sm font-medium text-emerald-700" : "text-sm font-medium text-amber-700"}>
                  {request.readiness.replaceAll("_", " ")}
                </span>
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
