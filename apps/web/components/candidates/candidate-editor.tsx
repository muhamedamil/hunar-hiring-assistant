"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { CandidateContactStatus } from "@/components/candidates/candidate-contact-status";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { createCandidate, updateCandidate } from "@/lib/candidates/api";
import { candidateKeys } from "@/lib/candidates/queries";
import type { Candidate, CandidateProfileInput } from "@/lib/candidates/types";

interface CandidateEditorState {
  fullName: string;
  currentTitle: string;
  currentCompany: string;
  location: string;
  email: string;
  phone: string;
}

function stateFromCandidate(candidate?: Candidate): CandidateEditorState {
  return {
    fullName: candidate?.full_name ?? "",
    currentTitle: candidate?.current_title ?? "",
    currentCompany: candidate?.current_company ?? "",
    location: candidate?.location ?? "",
    email: candidate?.email ?? "",
    phone: candidate?.phone_e164 ?? "",
  };
}

function toProfile(state: CandidateEditorState): CandidateProfileInput {
  return {
    full_name: state.fullName.trim(),
    current_title: state.currentTitle.trim() || null,
    current_company: state.currentCompany.trim() || null,
    location: state.location.trim() || null,
    email: state.email.trim() || null,
    phone: state.phone.trim() || null,
  };
}

function validationMessage(state: CandidateEditorState): string | null {
  if (!state.fullName.trim()) return "Candidate name is required.";
  if (state.fullName.trim().length > 200) return "Candidate name must be 200 characters or fewer.";
  if (state.phone.trim() && !state.phone.trim().startsWith("+")) {
    return "Phone must include an international country code, for example +91.";
  }
  return null;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function existingCandidateId(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== "CANDIDATE_ALREADY_EXISTS") return null;
  if (!error.details || typeof error.details !== "object") return null;
  const details = error.details as { existing_candidate_id?: unknown };
  return typeof details.existing_candidate_id === "string"
    ? details.existing_candidate_id
    : null;
}

export function CandidateEditor({ initialCandidate }: { initialCandidate?: Candidate }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [candidate, setCandidate] = useState<Candidate | undefined>(initialCandidate);
  const [state, setState] = useState<CandidateEditorState>(() => stateFromCandidate(initialCandidate));
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duplicateCandidateId, setDuplicateCandidateId] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: (profile: CandidateProfileInput) => createCandidate(profile),
  });
  const updateMutation = useMutation({
    mutationFn: ({
      candidateId,
      revision,
      profile,
    }: {
      candidateId: string;
      revision: number;
      profile: CandidateProfileInput;
    }) => updateCandidate(candidateId, revision, profile),
  });

  const pending = createMutation.isPending || updateMutation.isPending;

  function syncFromServer(nextCandidate: Candidate) {
    setCandidate(nextCandidate);
    setState(stateFromCandidate(nextCandidate));
    setError(null);
    setDuplicateCandidateId(null);
    void queryClient.invalidateQueries({ queryKey: candidateKeys.all });
    void queryClient.setQueryData(candidateKeys.detail(nextCandidate.id), nextCandidate);
  }

  async function handleSave() {
    const validation = validationMessage(state);
    if (validation) {
      setFeedback(null);
      setError(validation);
      setDuplicateCandidateId(null);
      return;
    }

    setFeedback(null);
    setError(null);
    setDuplicateCandidateId(null);

    try {
      if (!candidate) {
        const created = await createMutation.mutateAsync(toProfile(state));
        syncFromServer(created);
        setFeedback("Candidate created.");
        router.replace(`/candidates/${created.id}`);
        return;
      }

      const updated = await updateMutation.mutateAsync({
        candidateId: candidate.id,
        revision: candidate.revision,
        profile: toProfile(state),
      });
      syncFromServer(updated);
      setFeedback("Candidate changes saved.");
    } catch (mutationError) {
      const existingId = existingCandidateId(mutationError);
      setDuplicateCandidateId(existingId);
      setError(errorMessage(mutationError));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">Candidate Core</p>
          <h1 className="text-3xl font-semibold tracking-tight">
            {candidate ? candidate.full_name : "Add candidate"}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Maintain one global candidate identity. Job matching and outreach are added in later modules.
          </p>
        </div>
        {candidate ? (
          <div className="space-y-2 text-right">
            <CandidateContactStatus
              hasEmail={Boolean(candidate.email)}
              hasPhone={Boolean(candidate.phone_e164)}
            />
            <p className="text-xs text-slate-500">revision {candidate.revision}</p>
          </div>
        ) : null}
      </div>

      {feedback ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {feedback}
        </div>
      ) : null}

      {error ? (
        <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <div>{error}</div>
          {duplicateCandidateId ? (
            <Link href={`/candidates/${duplicateCandidateId}`} className="mt-2 inline-block font-medium underline">
              Open existing candidate
            </Link>
          ) : null}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Candidate profile</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="candidate-name">Full name</Label>
            <Input
              id="candidate-name"
              value={state.fullName}
              onChange={(event) => setState((current) => ({ ...current, fullName: event.target.value }))}
              placeholder="Sarah Ahmed"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="candidate-title">Current title</Label>
            <Input
              id="candidate-title"
              value={state.currentTitle}
              onChange={(event) => setState((current) => ({ ...current, currentTitle: event.target.value }))}
              placeholder="Backend Engineer"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="candidate-company">Company</Label>
            <Input
              id="candidate-company"
              value={state.currentCompany}
              onChange={(event) => setState((current) => ({ ...current, currentCompany: event.target.value }))}
              placeholder="Acme"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="candidate-location">Location</Label>
            <Input
              id="candidate-location"
              value={state.location}
              onChange={(event) => setState((current) => ({ ...current, location: event.target.value }))}
              placeholder="Bangalore"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="candidate-email">Email</Label>
            <Input
              id="candidate-email"
              type="email"
              value={state.email}
              onChange={(event) => setState((current) => ({ ...current, email: event.target.value }))}
              placeholder="sarah@example.com"
            />
          </div>

          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="candidate-phone">Phone</Label>
            <Input
              id="candidate-phone"
              type="tel"
              value={state.phone}
              onChange={(event) => setState((current) => ({ ...current, phone: event.target.value }))}
              placeholder="+91 98765 43210"
            />
            <p className="text-xs text-slate-500">
              Include the international country code. The backend stores canonical E.164 format.
            </p>
          </div>
        </CardContent>
      </Card>

      {candidate?.external_identities.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Provider identities</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {candidate.external_identities.map((identity) => (
              <div key={identity.id} className="rounded-lg border p-3 text-sm">
                <div className="font-medium capitalize">{identity.provider}</div>
                <div className="mt-1 text-slate-500">External ID: {identity.external_person_id}</div>
                {identity.profile_url ? (
                  <a
                    href={identity.profile_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-slate-700 underline"
                  >
                    Provider profile
                  </a>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="sticky bottom-4 flex justify-end rounded-xl border bg-white/95 p-4 shadow-lg backdrop-blur">
        <Button type="button" disabled={pending} onClick={handleSave}>
          {pending ? "Saving…" : candidate ? "Save changes" : "Create candidate"}
        </Button>
      </div>
    </div>
  );
}
