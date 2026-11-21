"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { HeartHandshake, MessageCircleHeart, PenLine, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { AiLabel, AiWaiting, Badge, Button, Card, CardHeader, ErrorBox } from "@/components/ui";
import { api } from "@/lib/api";
import type { Suggestion } from "@/lib/types";
import { cn, fmtDate, modelLabel } from "@/lib/utils";

export interface PrepPayload {
  summary?: string[];
  goal: string;
  agenda: string[];
  questions: string[];
  communication_tips: string[];
  difficult: { situation: string; how: string }[];
  wellbeing: string[];
  feedback?: { criterion: string; score: number | null; kind: "docenienie" | "rozwoj" | "dopytaj"; say: string; source_note_ids: number[] }[];
  watch_out?: string[];
}

const FEEDBACK_KIND = {
  docenienie: { label: "docenić", tone: "green" },
  rozwoj: { label: "do rozwoju", tone: "amber" },
  dopytaj: { label: "dopytać", tone: "slate" },
} as const;

export interface HrSignal {
  code: string;
  severity: "high" | "medium" | "info";
  title: string;
  message: string;
  evidence: number[];
  actions: string[];
}

export interface HrPartnerData {
  employee_id: number;
  full_name: string;
  risk: "high" | "medium" | "low";
  signals: HrSignal[];
  appreciation: { note_id: number; date: string; text: string; suggestion: string }[];
}

const KIND_LABEL = {
  opening: "rozmowy rozpoczynającej ocenę",
  feedback: "rozmowy z bieżącą informacją zwrotną",
  assessment: "rozmowy oceniającej",
  difficult: "trudnej rozmowy",
} as const;

export function ConversationPrep({ reviewId, kind, bare }: { reviewId: number; kind: keyof typeof KIND_LABEL; bare?: boolean }) {
  const [prep, setPrep] = useState<Suggestion<PrepPayload> | null>(null);
  const m = useMutation({
    mutationFn: () => api<Suggestion<PrepPayload>>(`/reviews/${reviewId}/ai/conversation-prep?kind=${kind}`, { method: "POST" }),
    onSuccess: setPrep,
  });
  const body = (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        {kind === "assessment"
          ? "Przed rozmową oceniającą: podsumowanie okresu, przebieg rozmowy, informacja zwrotna dla każdego kryterium (z odwołaniem do notatek), pytania i to, na co uważać."
          : `Wirtualny HR partner przygotuje cel, przebieg, pytania i wskazówki do ${KIND_LABEL[kind]} na podstawie dziennika obserwacji.`}
      </p>
      <Button variant="ai" className="w-full" onClick={() => m.mutate()} loading={m.isPending}>
        <PenLine className="h-4 w-4" aria-hidden /> Przygotuj mnie do {KIND_LABEL[kind]}
      </Button>
      <AiWaiting active={m.isPending} typical="40–90 s" />
      <ErrorBox error={m.error} />
      {prep && <PrepView prep={prep} />}
    </div>
  );
  if (bare) return body;
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <HeartHandshake className="h-4 w-4 text-ai" aria-hidden /> {kind === "assessment" ? "HR partner: przygotowanie do rozmowy oceniającej" : "HR partner"}
          </span>
        }
      />
      <div className="p-4">{body}</div>
    </Card>
  );
}

function PrepView({ prep }: { prep: Suggestion<PrepPayload> }) {
  const p = prep.payload;
  return (
    <div className="space-y-3 ai-draft rounded-md p-3 text-sm">
      <AiLabel model={modelLabel(prep.model)} />
      {p.summary && p.summary.length > 0 && (
        <Section title="Podsumowanie okresu oceny">
          <ul className="list-disc space-y-0.5 pl-5">
            {p.summary.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </Section>
      )}
      <Section title="Cel rozmowy">
        <p>{p.goal}</p>
      </Section>
      <Section title="Przebieg">
        <ol className="list-decimal space-y-0.5 pl-5">
          {p.agenda.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ol>
      </Section>
      <Section title="Pytania">
        <ul className="list-disc space-y-0.5 pl-5">
          {p.questions.map((q) => (
            <li key={q}>{q}</li>
          ))}
        </ul>
      </Section>
      <Section title="Wskazówki komunikacyjne">
        <ul className="list-disc space-y-0.5 pl-5">
          {p.communication_tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </Section>
      {p.difficult.length > 0 && (
        <Section title="Trudne sytuacje">
          <ul className="space-y-1.5">
            {p.difficult.map((d) => (
              <li key={d.situation}>
                <strong>{d.situation}.</strong> {d.how}
              </li>
            ))}
          </ul>
        </Section>
      )}
      {p.watch_out && p.watch_out.length > 0 && (
        <Section title="Na co uważać">
          <ul className="list-disc space-y-0.5 pl-5">
            {p.watch_out.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Section>
      )}
      {p.feedback && p.feedback.length > 0 && (
        <Section title="Informacja zwrotna - kryterium po kryterium">
          <ul className="space-y-2">
            {p.feedback.map((f) => {
              const k = FEEDBACK_KIND[f.kind] ?? FEEDBACK_KIND.dopytaj;
              return (
                <li key={f.criterion} className="rounded-md border border-ai-border/50 bg-white/70 p-2">
                  <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                    <strong>{f.criterion}</strong>
                    {f.score != null && <span className="text-xs text-muted">{f.score} pkt</span>}
                    <Badge tone={k.tone}>{k.label}</Badge>
                  </div>
                  <p>{f.say}</p>
                  {f.source_note_ids.length > 0 && (
                    <p className="mt-0.5 text-xs text-muted">Notatki: {f.source_note_ids.map((id) => `#${id}`).join(", ")}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      {p.wellbeing.length > 0 && (
        <Section title="Dobrostan">
          <ul className="list-disc space-y-0.5 pl-5">
            {p.wellbeing.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="mb-0.5 text-xs font-semibold uppercase tracking-wide text-ai">{title}</h4>
      {children}
    </div>
  );
}

const SEV: Record<HrSignal["severity"], string> = {
  high: "border-l-red-600",
  medium: "border-l-amber-500",
  info: "border-l-slate-300",
};

export function HrPartnerPanel({ employeeId, onShowNote }: { employeeId: number; onShowNote?: (id: number) => void }) {
  const { data, error } = useQuery({ queryKey: ["hr-partner", employeeId], queryFn: () => api<HrPartnerData>(`/employees/${employeeId}/hr-partner`) });
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <HeartHandshake className="h-4 w-4 text-ai" aria-hidden /> HR partner: kondycja i docenianie
          </span>
        }
        subtitle="Podpowiedzi do rozmowy wspierającej, nie diagnoza. Nie wpływają na ocenę i widzi je tylko przełożony."
      />
      <div className="space-y-3 p-4 text-sm">
        {data.appreciation.length > 0 && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3">
            <h4 className="mb-1 flex items-center gap-1.5 font-medium text-emerald-900">
              <ThumbsUp className="h-4 w-4" aria-hidden /> Warto docenić
            </h4>
            <ul className="space-y-1 text-emerald-900">
              {data.appreciation.map((a) => (
                <li key={a.note_id}>
                  <button className="text-left hover:underline" onClick={() => onShowNote?.(a.note_id)}>
                    {fmtDate(a.date)}: {a.text}
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-emerald-800">{data.appreciation[0].suggestion}</p>
          </div>
        )}
        {data.signals.length === 0 && <p className="text-muted">Brak sygnałów wymagających uwagi.</p>}
        {data.signals.map((s) => (
          <details key={s.code} className={cn("rounded-md border border-border border-l-4 bg-white px-3 py-2", SEV[s.severity])} open={s.severity === "high"}>
            <summary className="cursor-pointer font-medium">
              {s.title} {s.severity === "high" && <Badge tone="red">pilne</Badge>}
            </summary>
            <p className="mt-1 text-slate-700">{s.message}</p>
            {s.evidence.length > 0 && (
              <p className="mt-1 text-xs text-muted">
                Na podstawie notatek:{" "}
                {s.evidence.map((id) => (
                  <button key={id} className="mr-1 text-primary hover:underline" onClick={() => onShowNote?.(id)}>
                    #{id}
                  </button>
                ))}
              </p>
            )}
            <h5 className="mt-2 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
              <MessageCircleHeart className="h-3.5 w-3.5" aria-hidden /> Co możesz zrobić
            </h5>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-5 text-slate-700">
              {s.actions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </Card>
  );
}

export interface TeamSignal {
  employee_id: number;
  risk: "high" | "medium" | "low";
  titles: string[];
  appreciation: number;
}

export function RiskBadge({ s }: { s: TeamSignal | undefined }) {
  if (!s) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {s.risk === "high" && (
        <Badge tone="red" title={s.titles.join(", ")}>
          wymaga rozmowy
        </Badge>
      )}
      {s.risk === "medium" && (
        <Badge tone="amber" title={s.titles.join(", ")}>
          {s.titles[0] ?? "uwaga"}
        </Badge>
      )}
      {s.appreciation > 0 && <Badge tone="green">warto docenić</Badge>}
    </span>
  );
}
