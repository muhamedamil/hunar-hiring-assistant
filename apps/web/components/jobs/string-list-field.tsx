"use client";

import { useState } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface StringListFieldProps {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  maxItems?: number;
}

export function StringListField({
  label,
  value,
  onChange,
  placeholder,
  disabled = false,
  maxItems,
}: StringListFieldProps) {
  const [draft, setDraft] = useState("");

  function addValue() {
    const normalized = draft.trim();
    if (!normalized) return;
    if (maxItems !== undefined && value.length >= maxItems) return;
    if (value.some((item) => item.toLowerCase() === normalized.toLowerCase())) {
      setDraft("");
      return;
    }
    onChange([...value, normalized]);
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex gap-2">
        <Input
          value={draft}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addValue();
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled={disabled || !draft.trim() || (maxItems !== undefined && value.length >= maxItems)}
          onClick={addValue}
        >
          Add
        </Button>
      </div>
      {value.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {value.map((item) => (
            <span
              key={item.toLowerCase()}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
            >
              {item}
              {!disabled ? (
                <button
                  type="button"
                  aria-label={`Remove ${item}`}
                  onClick={() => onChange(value.filter((candidate) => candidate !== item))}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
