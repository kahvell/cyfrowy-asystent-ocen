"use client";

// Etap I (§ 5): AI dla oceniającego - dobór kryteriów dodatkowych na bazie historii;
// AI dla ocenianego - przygotowanie do rozmowy rozpoczynającej (kryteria, własne cele, zgoda / brak zgody).

import { useMutation } from "@tanstack/react-query";
import { Check, ListChecks, MessageSquareQuote, PenLine, Plus, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useReviewMutation } from "@/components/process";
import { AiLabel, AiWaiting, Button, Card, CardHeader, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import type { Review, Suggestion } from "@/lib/types";
import { modelLabel } from "@/lib/utils";

const MAX_ADDITIONAL = 3;

type CriteriaPayload = {
  proposals: { criterion_id: number; criterion_code: string; name: string; why: string; evidence: string[] }[];
  talking_points: string[];
};

type EmployeePrepPayload = {
  goal: string;
  before: string[];
  criteria_guide: { criterion: string; what_it_means: string; ask: string }[];
  my_goals: string[];
  agree_disagree: { situation: string; how: string }[];
  questions: string[];
  rights: string[];
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ai">{title}</h4>
      {children}
    </div>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-0.5 pl-5">
      {items.map((t) => (
        <li key={t}>{t}</li>
      ))}
    </ul>
  );
}

/** Oceniający: propozycja kryteriów dodatkowych (maks. 3) z uzasadnieniem z danych. Wybór zawsze należy do człowieka. */
export function CriteriaSuggestPanel({ review }: { review: Review }) {
  const [sugg, setSugg] = useState<Suggestion<CriteriaPayload> | null>(null);
  const [decided, setDecided] = useState<string | null>(null);
  const patch = useReviewMutation(review.id);
  const gen = useMutation({
    mutationFn: () => api<Suggestion<CriteriaPayload>>(`/reviews/${review.id}/ai/suggest-criteria`, { method: "POST" }),
    onSuccess: (s) => {
      setSugg(s);
      setDecided(null);
    },
  });
  const decide = useMutation({
    mutationFn: (status: "accepted" | "edited" | "rejected") =>
      api(`/ai-suggestions/${sugg!.id}/decision`, { method: "POST", json: { status } }),
    onSuccess: (_, status) => setDecided(status),
  });

  const chosen = review.criteria.filter((c) => c.is_additional).map((c) => c.criterion_id);
  const proposals = sugg?.payload.proposals ?? [];
  const add = (ids: number[]) => {
    const next = [...chosen, ...ids.filter((id) => !chosen.includes(id))].slice(0, MAX_ADDITIONAL);
    patch.mutate(
      { path: "", method: "PATCH", json: { additional_criterion_ids: next } },
      {
        onSuccess: () => {
          if (!decided && sugg) decide.mutate(proposals.every((p) => next.includes(p.criterion_id)) ? "accepted" : "edited");
        },
      },
    );
  };
  const missing = proposals.filter((p) => !chosen.includes(p.criterion_id)).map((p) => p.criterion_id);

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-ai" aria-hidden /> Dobór kryteriów dodatkowych
          </span>
        }
        subtitle="§ 5 ust. 2: nie więcej niż 3, wybiera oceniający"
      />
      <div className="space-y-3 p-4 text-sm">
        <p className="text-slate-600">
          Asystent przeanalizuje opis stanowiska, poprzednią ocenę i IPRZ oraz kryteria wybierane dla tego stanowiska w urzędzie i zaproponuje
          kryteria dodatkowe z uzasadnieniem.
        </p>
        <Button variant="ai" className="w-full" onClick={() => gen.mutate()} loading={gen.isPending}>
          <PenLine className="h-4 w-4" aria-hidden /> Zaproponuj kryteria dodatkowe
        </Button>
        <AiWaiting active={gen.isPending} typical="20–60 s" />
        <ErrorBox error={gen.error || patch.error} />

        {sugg && (
          <div className="ai-draft space-y-3 rounded-md p-3">
            <div className="flex items-center justify-between gap-2">
              <AiLabel model={modelLabel(sugg.model)} />
              {!decided && (
                <button onClick={() => decide.mutate("rejected")} className="text-slate-500 hover:text-slate-800" aria-label="Odrzuć propozycję">
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
            {proposals.length === 0 ? (
              <p className="text-slate-700">Brak danych, które wskazywałyby konkretne kryterium - wybierz je na podstawie rozmowy z pracownikiem.</p>
            ) : (
              <ol className="space-y-3">
                {proposals.map((p) => {
                  const inSheet = chosen.includes(p.criterion_id);
                  const full = !inSheet && chosen.length >= MAX_ADDITIONAL;
                  return (
                    <li key={p.criterion_id} className="rounded-md border border-ai-border/60 bg-white/70 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <strong className="font-serif text-[15px]">{p.name}</strong>
                        {inSheet ? (
                          <span className="inline-flex shrink-0 items-center gap-1 text-xs text-emerald-700">
                            <Check className="h-3.5 w-3.5" aria-hidden /> w arkuszu
                          </span>
                        ) : (
                          <Button size="sm" variant="secondary" disabled={full || patch.isPending} onClick={() => add([p.criterion_id])} title={full ? "Wybrano już 3 kryteria dodatkowe" : undefined}>
                            <Plus className="h-3.5 w-3.5" aria-hidden /> Dodaj
                          </Button>
                        )}
                      </div>
                      <p className="mt-1 text-slate-700">{p.why}</p>
                      {p.evidence.length > 0 && (
                        <ul className="mt-1.5 space-y-0.5 text-xs text-muted">
                          {p.evidence.map((e) => (
                            <li key={e}>· {e}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
            {missing.length > 1 && chosen.length + missing.length <= MAX_ADDITIONAL && (
              <Button size="sm" className="w-full" onClick={() => add(missing)} loading={patch.isPending}>
                Dodaj wszystkie propozycje do arkusza
              </Button>
            )}
            {sugg.payload.talking_points.length > 0 && (
              <Section title="Do omówienia w rozmowie rozpoczynającej">
                <Bullets items={sugg.payload.talking_points} />
              </Section>
            )}
            {decided && (
              <p className="text-xs text-muted">
                Decyzja zapisana w dzienniku zdarzeń: {decided === "rejected" ? "odrzucono" : decided === "accepted" ? "przyjęto" : "przyjęto częściowo"}.
              </p>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

/** Oceniany: jak przygotować się do rozmowy rozpoczynającej - zrozumieć kryteria, przedstawić własne cele,
 *  rzeczowo zgodzić się albo nie zgodzić z kryterium. Materiał widzi tylko pracownik. */
export function EmployeeOpeningPrep({ reviewId }: { reviewId: number }) {
  const [prep, setPrep] = useState<Suggestion<EmployeePrepPayload> | null>(null);
  const m = useMutation({
    mutationFn: () => api<Suggestion<EmployeePrepPayload>>(`/reviews/${reviewId}/ai/employee-opening-prep`, { method: "POST" }),
    onSuccess: setPrep,
  });
  const p = prep?.payload;
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <MessageSquareQuote className="h-4 w-4 text-ai" aria-hidden /> Twoje przygotowanie do rozmowy
          </span>
        }
        subtitle="Rozmowa rozpoczynająca (§ 5): kryteria, oczekiwania i Twoje cele"
      />
      <div className="space-y-3 p-4 text-sm">
        <p className="text-slate-600">
          Asystent podpowie, jak rozmawiać o swoich celach, jak dopytać o kryteria i jak rzeczowo zgodzić się albo nie zgodzić z kryterium. Widzisz to
          tylko Ty.
        </p>
        <Button variant="ai" className="w-full" onClick={() => m.mutate()} loading={m.isPending}>
          <PenLine className="h-4 w-4" aria-hidden /> Przygotuj mnie do rozmowy
        </Button>
        <AiWaiting active={m.isPending} typical="30–90 s" />
        <ErrorBox error={m.error} />
        {prep && p && (
          <div className="ai-draft space-y-3 rounded-md p-3">
            <AiLabel model={modelLabel(prep.model)} />
            <Section title="Cel rozmowy">
              <p>{p.goal}</p>
            </Section>
            <Section title="Przed rozmową">
              <Bullets items={p.before} />
            </Section>
            <Section title="Kryteria - co znaczą i o co zapytać">
              <ul className="space-y-2">
                {p.criteria_guide.map((g) => (
                  <li key={g.criterion}>
                    <strong>{g.criterion}.</strong> {g.what_it_means}
                    <span className="mt-0.5 block italic text-slate-600">„{g.ask}”</span>
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Twoje cele">
              <Bullets items={p.my_goals} />
            </Section>
            <Section title="Gdy się zgadzasz - i gdy nie">
              <ul className="space-y-1.5">
                {p.agree_disagree.map((d) => (
                  <li key={d.situation}>
                    <strong>{d.situation}.</strong> {d.how}
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Pytania do przełożonego">
              <Bullets items={p.questions} />
            </Section>
            <Section title="Warto wiedzieć">
              <Bullets items={p.rights} />
            </Section>
          </div>
        )}
      </div>
    </Card>
  );
}
