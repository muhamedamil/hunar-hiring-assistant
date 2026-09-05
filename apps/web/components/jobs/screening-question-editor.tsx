"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ScreeningAnswerType, ScreeningQuestionInput } from "@/lib/jobs/types";

interface EditableQuestion extends ScreeningQuestionInput {
  client_key: string;
}

interface ScreeningQuestionEditorProps {
  value: EditableQuestion[];
  onChange: (value: EditableQuestion[]) => void;
  disabled?: boolean;
}

const answerTypes: ScreeningAnswerType[] = ["yes_no", "short_text", "number", "choice"];

function newQuestion(): EditableQuestion {
  return {
    client_key: globalThis.crypto?.randomUUID?.() ?? `question-${Date.now()}-${Math.random()}`,
    key: "",
    prompt: "",
    answer_type: "short_text",
    required: true,
    options: [],
  };
}

export function ScreeningQuestionEditor({
  value,
  onChange,
  disabled = false,
}: ScreeningQuestionEditorProps) {
  function update(index: number, patch: Partial<EditableQuestion>) {
    onChange(value.map((question, candidateIndex) => (candidateIndex === index ? { ...question, ...patch } : question)));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <div className="space-y-4">
      {value.map((question, index) => (
        <div key={question.client_key} className="rounded-lg border border-slate-200 p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="text-sm font-medium">Question {index + 1}</div>
            {!disabled ? (
              <div className="flex gap-1">
                <Button type="button" variant="ghost" size="sm" disabled={index === 0} onClick={() => move(index, -1)}>
                  <ArrowUp className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="sm" disabled={index === value.length - 1} onClick={() => move(index, 1)}>
                  <ArrowDown className="h-4 w-4" />
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => onChange(value.filter((_, candidateIndex) => candidateIndex !== index))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ) : null}
          </div>

          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="space-y-2">
              <Label>Question</Label>
              <Textarea
                disabled={disabled}
                value={question.prompt}
                onChange={(event) => update(index, { prompt: event.target.value })}
                className="min-h-24"
              />
            </div>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Result key</Label>
                <Input
                  disabled={disabled}
                  value={question.key}
                  placeholder="python_experience"
                  onChange={(event) => update(index, { key: event.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label>Answer type</Label>
                <select
                  disabled={disabled}
                  value={question.answer_type}
                  onChange={(event) => {
                    const answerType = event.target.value as ScreeningAnswerType;
                    update(index, { answer_type: answerType, options: answerType === "choice" ? question.options : [] });
                  }}
                  className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm disabled:opacity-50"
                >
                  {answerTypes.map((type) => (
                    <option key={type} value={type}>
                      {type.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={question.required}
                  disabled={disabled}
                  onChange={(event) => update(index, { required: event.target.checked })}
                />
                Required
              </label>
            </div>
          </div>

          {question.answer_type === "choice" ? (
            <div className="mt-4 space-y-2">
              <Label>Choices</Label>
              <Input
                disabled={disabled}
                value={question.options.join(", ")}
                placeholder="Yes, No"
                onChange={(event) =>
                  update(index, {
                    options: event.target.value
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean)
                      .slice(0, 10),
                  })
                }
              />
              <p className="text-xs text-slate-500">Enter 2–10 comma-separated choices.</p>
            </div>
          ) : null}
        </div>
      ))}

      {!disabled && value.length < 10 ? (
        <Button type="button" variant="outline" onClick={() => onChange([...value, newQuestion()])}>
          <Plus className="mr-2 h-4 w-4" />
          Add question
        </Button>
      ) : null}
    </div>
  );
}

export type { EditableQuestion };
