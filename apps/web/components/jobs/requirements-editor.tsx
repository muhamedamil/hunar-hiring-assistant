"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StringListField } from "@/components/jobs/string-list-field";
import type {
  EmploymentType,
  JobRequirements,
  SeniorityLevel,
  WorkArrangement,
} from "@/lib/jobs/types";

const seniorityOptions: SeniorityLevel[] = [
  "intern",
  "entry",
  "mid",
  "senior",
  "lead",
  "manager",
  "director",
  "executive",
];

const employmentOptions: EmploymentType[] = [
  "full_time",
  "part_time",
  "contract",
  "internship",
  "temporary",
  "other",
];

const workArrangementOptions: WorkArrangement[] = ["onsite", "hybrid", "remote"];

interface RequirementsEditorProps {
  value: JobRequirements;
  onChange: (value: JobRequirements) => void;
  disabled?: boolean;
}

export function RequirementsEditor({ value, onChange, disabled = false }: RequirementsEditorProps) {
  function update<K extends keyof JobRequirements>(key: K, next: JobRequirements[K]) {
    onChange({ ...value, [key]: next });
  }

  return (
    <div className="grid gap-5">
      <StringListField
        label="Alternate search titles"
        value={value.alternate_titles}
        onChange={(items) => update("alternate_titles", items)}
        placeholder="Backend Engineer"
        disabled={disabled}
        maxItems={5}
      />
      <div className="grid gap-5 md:grid-cols-2">
        <StringListField
          label="Required skills"
          value={value.required_skills}
          onChange={(items) => update("required_skills", items)}
          placeholder="Python"
          disabled={disabled}
          maxItems={20}
        />
        <StringListField
          label="Preferred skills"
          value={value.preferred_skills}
          onChange={(items) => update("preferred_skills", items)}
          placeholder="AWS"
          disabled={disabled}
          maxItems={20}
        />
      </div>
      <StringListField
        label="Locations"
        value={value.locations}
        onChange={(items) => update("locations", items)}
        placeholder="Bangalore"
        disabled={disabled}
        maxItems={10}
      />
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2">
          <Label htmlFor="minimum-experience">Minimum experience</Label>
          <Input
            id="minimum-experience"
            type="number"
            min={0}
            max={50}
            disabled={disabled}
            value={value.min_years_experience ?? ""}
            onChange={(event) => {
              const next = event.target.value;
              update("min_years_experience", next === "" ? null : Number(next));
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="seniority">Seniority</Label>
          <select
            id="seniority"
            multiple
            size={4}
            disabled={disabled}
            value={value.seniority}
            onChange={(event) =>
              update(
                "seniority",
                Array.from(
                  event.currentTarget.selectedOptions,
                  (option) => option.value as SeniorityLevel,
                ).slice(0, 5),
              )
            }
            className="min-h-24 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm disabled:opacity-50"
          >
            {seniorityOptions.map((option) => (
              <option key={option} value={option}>
                {option.replaceAll("_", " ")}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">Use Ctrl/Cmd to select multiple levels.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="employment-type">Employment type</Label>
          <select
            id="employment-type"
            disabled={disabled}
            value={value.employment_type ?? ""}
            onChange={(event) =>
              update(
                "employment_type",
                event.target.value ? (event.target.value as EmploymentType) : null,
              )
            }
            className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm disabled:opacity-50"
          >
            <option value="">Unspecified</option>
            {employmentOptions.map((option) => (
              <option key={option} value={option}>
                {option.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="work-arrangement">Work arrangement</Label>
          <select
            id="work-arrangement"
            disabled={disabled}
            value={value.work_arrangement ?? ""}
            onChange={(event) =>
              update(
                "work_arrangement",
                event.target.value ? (event.target.value as WorkArrangement) : null,
              )
            }
            className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm disabled:opacity-50"
          >
            <option value="">Unspecified</option>
            {workArrangementOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
