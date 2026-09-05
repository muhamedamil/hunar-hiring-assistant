"use client";

import { Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface JobDescriptionSectionProps {
  title: string;
  companyName: string;
  description: string;
  disabled: boolean;
  analyzing: boolean;
  onTitleChange: (value: string) => void;
  onCompanyNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAnalyze: () => void;
}

export function JobDescriptionSection({
  title,
  companyName,
  description,
  disabled,
  analyzing,
  onTitleChange,
  onCompanyNameChange,
  onDescriptionChange,
  onAnalyze,
}: JobDescriptionSectionProps) {
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="job-title">Job title</Label>
          <Input
            id="job-title"
            disabled={disabled}
            value={title}
            maxLength={200}
            onChange={(event) => onTitleChange(event.target.value)}
            placeholder="Senior Python Engineer"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="company-name">Company</Label>
          <Input
            id="company-name"
            disabled={disabled}
            value={companyName}
            maxLength={200}
            onChange={(event) => onCompanyNameChange(event.target.value)}
            placeholder="Hunar.ai"
          />
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="job-description">Job description</Label>
          {!disabled ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={analyzing || description.trim().length < 20}
              onClick={onAnalyze}
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {analyzing ? "Analyzing…" : "Analyze with AI"}
            </Button>
          ) : null}
        </div>
        <Textarea
          id="job-description"
          disabled={disabled}
          value={description}
          maxLength={20000}
          onChange={(event) => onDescriptionChange(event.target.value)}
          placeholder="Paste the complete job description here…"
          className="min-h-56"
        />
        <div className="text-right text-xs text-slate-400">{description.length}/20,000</div>
      </div>
    </div>
  );
}
