"use client";

// Sprawdzanie celów IPR wg SMART: oceny S/M/A/R/T liczą jawne reguły w kodzie, model proponuje lepsze sformułowanie
// celu i miernika. Przełożony decyduje, czy propozycję zastosować.

import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { AiLabel, Button } from "./ui";

export type SmartCheck = {
  index: number;
  specific: boolean;
  measurable: boolean;
  achievable: boolean;
  relevant: boolean;
  time_bound: boolean;
  issues: string[];
  improved_goal: string;
  improved_measure: string;
};

const LETTERS: [keyof SmartCheck, string, string][] = [
  ["specific", "S", "konkretny"],
  ["measurable", "M", "mierzalny"],
  ["achievable", "A", "osiągalny (są działania)"],
  ["relevant", "R", "istotny (powiązany z kryterium)"],
  ["time_bound", "T", "określony w czasie"],
];

export function SmartResult({
  check,
  model,
  goal,
  measure,
  editable,
  onApply,
}: {
  check: SmartCheck;
  model: string;
  goal: string;
  measure: string;
  editable: boolean;
  onApply: (patch: { goal?: string; success_measure?: string }) => void;
}) {
  const ok = check.issues.length === 0;
  const betterGoal = check.improved_goal && check.improved_goal.trim() !== goal.trim() ? check.improved_goal : null;
  const betterMeasure = check.improved_measure && check.improved_measure.trim() !== measure.trim() ? check.improved_measure : null;
  return (
    <div className={cn("rounded-md p-3 text-sm", ok ? "border border-emerald-200 bg-emerald-50" : "ai-draft")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-primary">SMART</span>
        {LETTERS.map(([key, letter, label]) => {
          const pass = check[key] as boolean;
          return (
            <span
              key={letter}
              title={label}
              className={cn(
                "inline-flex items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-xs font-semibold",
                pass ? "border-emerald-300 bg-white text-emerald-800" : "border-red-300 bg-red-50 text-red-800",
              )}
            >
              {letter}
              {pass ? <Check className="h-3 w-3" aria-hidden /> : <X className="h-3 w-3" aria-hidden />}
              <span className="sr-only">{label}</span>
            </span>
          );
        })}
        {ok && <span className="text-xs text-emerald-800">Cel spełnia kryteria SMART.</span>}
      </div>
      {!ok && (
        <>
          <ul className="mt-2 list-disc space-y-0.5 pl-5 text-slate-700">
            {check.issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
          {(betterGoal || betterMeasure) && (
            <div className="mt-2 space-y-2">
              <AiLabel model={model} />
              {betterGoal && (
                <div>
                  <div className="text-xs text-muted">Propozycja celu</div>
                  <p>{betterGoal}</p>
                  {editable && (
                    <Button size="sm" variant="secondary" className="mt-1" onClick={() => onApply({ goal: betterGoal })}>
                      Zastosuj cel
                    </Button>
                  )}
                </div>
              )}
              {betterMeasure && (
                <div>
                  <div className="text-xs text-muted">Propozycja miernika</div>
                  <p>{betterMeasure}</p>
                  {editable && (
                    <Button size="sm" variant="secondary" className="mt-1" onClick={() => onApply({ success_measure: betterMeasure })}>
                      Zastosuj miernik
                    </Button>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
