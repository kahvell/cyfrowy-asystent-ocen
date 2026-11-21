"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, Check, Info, MessagesSquare, Pencil, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { ComparePayload, DraftPayload, Review, Suggestion, Warning } from "@/lib/types";
import { cn, modelLabel, scaleLabel } from "@/lib/utils";
import { AiLabel, Badge, Button, ErrorBox, Textarea } from "./ui";

export function SourceChip({ id, onClick }: { id: number; onClick?: (id: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onClick?.(id)}
      className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 ring-1 ring-slate-200 hover:bg-amber-100"
      title="Pokaż notatkę źródłową"
    >
      #{id}
    </button>
  );
}

export function DraftSuggestion({
  suggestion,
  reviewId,
  onShowNote,
  onApplyScore,
  onClose,
}: {
  suggestion: Suggestion<DraftPayload>;
  reviewId: number;
  onShowNote: (id: number) => void;
  onApplyScore: (score: number) => void;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const p = suggestion.payload;
  const fullText = p.sentences.map((s) => s.text).join(" ");
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(fullText);
  const decide = useMutation({
    mutationFn: (body: { status: "accepted" | "edited" | "rejected"; final_text?: string }) =>
      api(`/ai-suggestions/${suggestion.id}/decision`, { method: "POST", json: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review", reviewId] });
      onClose();
    },
  });

  return (
    <div className="mt-3 rounded-md border border-violet-200 bg-ai-bg p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <AiLabel model={modelLabel(suggestion.model)} />
        <button onClick={onClose} aria-label="Zamknij propozycję" className="text-slate-500 hover:text-slate-800">
          <X className="h-4 w-4" />
        </button>
      </div>
      {p.sentences.length === 0 ? (
        <p className="text-sm text-slate-700">{p.rationale}</p>
      ) : editing ? (
        <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} aria-label="Edytuj propozycję" />
      ) : (
        <ol className="space-y-1.5 text-sm">
          {p.sentences.map((s, i) => (
            <li key={i} className={cn(s.unsupported && "rounded bg-red-50 px-1")}>
              {s.text}{" "}
              <span className="inline-flex gap-1 align-middle">
                {s.source_note_ids.map((id) => (
                  <SourceChip key={id} id={id} onClick={onShowNote} />
                ))}
                {s.unsupported && <Badge tone="red">brak źródła - zweryfikuj</Badge>}
              </span>
            </li>
          ))}
        </ol>
      )}
      {p.sentences.length > 0 && (
        <>
          <p className="mt-3 text-xs text-slate-600">
            Na podstawie {p.notes_used} notatek z dziennika. {p.rationale}
          </p>
          {p.proposed_score && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <span>
                Sugerowany poziom: <strong>{p.proposed_score} pkt</strong> ({scaleLabel(p.proposed_score)})
              </span>
              <Button size="sm" variant="secondary" onClick={() => onApplyScore(p.proposed_score!)}>
                Ustaw ten poziom
              </Button>
              <span className="text-xs text-muted">ocenę zawsze wystawia przełożony</span>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {editing ? (
              <Button size="sm" onClick={() => decide.mutate({ status: "edited", final_text: text })} loading={decide.isPending}>
                <Check className="h-4 w-4" aria-hidden /> Zapisz moją wersję
              </Button>
            ) : (
              <>
                <Button size="sm" onClick={() => decide.mutate({ status: "accepted" })} loading={decide.isPending}>
                  <Check className="h-4 w-4" aria-hidden /> Akceptuj
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                  <Pencil className="h-4 w-4" aria-hidden /> Edytuj
                </Button>
              </>
            )}
            <Button size="sm" variant="danger" onClick={() => decide.mutate({ status: "rejected" })} disabled={decide.isPending}>
              <X className="h-4 w-4" aria-hidden /> Odrzuć
            </Button>
          </div>
          <ErrorBox error={decide.error} />
        </>
      )}
    </div>
  );
}

const SEV = {
  critical: { icon: AlertOctagon, cls: "border-red-200 bg-red-50", tone: "red" as const, label: "krytyczne" },
  warning: { icon: AlertTriangle, cls: "border-amber-200 bg-amber-50", tone: "amber" as const, label: "ostrzeżenie" },
  info: { icon: Info, cls: "border-blue-200 bg-blue-50", tone: "blue" as const, label: "informacja" },
};

export function WarningsList({
  warnings,
  review,
  onShowNote,
  onJump,
}: {
  warnings: Warning[];
  review: Review;
  onShowNote: (id: number) => void;
  onJump: (criterionId: number) => void;
}) {
  if (warnings.length === 0)
    return <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">Nie wykryto problemów. Pamiętaj, że ostateczna ocena należy do Ciebie.</p>;
  const order = { critical: 0, warning: 1, info: 2 };
  return (
    <ul className="space-y-2">
      {[...warnings]
        .sort((a, b) => order[a.severity] - order[b.severity])
        .map((w, i) => {
          const s = SEV[w.severity];
          const Icon = s.icon;
          const crit = review.criteria.find((c) => c.criterion_id === w.criterion_id);
          return (
            <li key={i} className={cn("rounded-md border p-3 text-sm", s.cls)}>
              <div className="flex items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-medium">{w.title}</span>
                    <Badge tone={s.tone}>{s.label}</Badge>
                    {w.source === "ai" ? (
                      <Badge tone="violet">
                        <Sparkles className="h-3 w-3" aria-hidden /> AI
                      </Badge>
                    ) : (
                      <Badge>reguła</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-slate-700">{w.message}</p>
                  {w.suggestion && <p className="mt-1 text-slate-600">→ {w.suggestion}</p>}
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {w.evidence
                      .filter((e): e is number => typeof e === "number")
                      .map((id) => (
                        <SourceChip key={id} id={id} onClick={onShowNote} />
                      ))}
                    {crit && (
                      <button onClick={() => onJump(crit.criterion_id)} className="text-xs text-primary hover:underline">
                        przejdź do kryterium
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
    </ul>
  );
}

export function ComparePanel({ suggestion }: { suggestion: Suggestion<ComparePayload> }) {
  const p = suggestion.payload;
  return (
    <div className="space-y-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="py-1 font-medium">Kryterium</th>
            <th className="py-1 text-center font-medium">Przełożony</th>
            <th className="py-1 text-center font-medium">Samoocena</th>
          </tr>
        </thead>
        <tbody>
          {p.rows.map((r) => (
            <tr key={r.criterion_id} className="border-t border-border align-top">
              <td className="py-1.5 pr-2">
                {r.name}
                {r.comment && <div className="text-xs italic text-muted">„{r.comment}”</div>}
              </td>
              <td className="py-1.5 text-center">{r.manager_score ?? "-"}</td>
              <td className="py-1.5 text-center">
                <span
                  className={cn(
                    "rounded px-1.5",
                    r.level === "major" && "bg-red-100 font-semibold text-red-800",
                    r.level === "minor" && "bg-amber-100 text-amber-900",
                  )}
                >
                  {r.self_score ?? "-"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {p.summary && <p className="text-sm text-slate-700">{p.summary}</p>}
      <div className="rounded-md border border-violet-200 bg-ai-bg p-3">
        <div className="mb-2 flex items-center gap-2">
          <MessagesSquare className="h-4 w-4 text-ai" aria-hidden />
          <span className="text-sm font-medium">Pytania do rozmowy oceniającej (§ 10)</span>
        </div>
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          {p.questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ol>
        <div className="mt-2">
          <AiLabel model={modelLabel(suggestion.model)} />
        </div>
      </div>
    </div>
  );
}
