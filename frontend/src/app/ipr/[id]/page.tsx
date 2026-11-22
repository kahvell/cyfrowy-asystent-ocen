"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, GraduationCap, PenLine, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useMe } from "@/components/app-shell";
import { LearningMix, MixTags } from "@/components/learning-mix";
import { SmartResult, type SmartCheck } from "@/components/smart";
import { useCriteria } from "@/components/notes";
import { AiLabel, AiWaiting, Badge, Button, Card, ErrorBox, Input, Label, PageTitle, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { IPR, IPRGoal, Training } from "@/lib/types";
import { fmtDate, modelLabel } from "@/lib/utils";

const IPR_STATUS: Record<IPR["status"], string> = {
  draft: "projekt",
  established: "ustalony przez przełożonego",
  accepted: "zaakceptowany - czeka na zatwierdzenie DG",
  approved: "zatwierdzony przez dyrektora generalnego",
};

export default function IPRPage() {
  const { id } = useParams<{ id: string }>();
  const iprId = Number(id);
  const { data: ipr, error, isPending } = useQuery({ queryKey: ["ipr", iprId], queryFn: () => api<IPR>(`/ipr/${iprId}`) });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  return <IPRForm key={`${ipr.status}:${ipr.ai?.prompt_version}:${ipr.goals.length}`} ipr={ipr} />;
}

function IPRForm({ ipr }: { ipr: IPR }) {
  const iprId = ipr.id;
  const me = useMe();
  const qc = useQueryClient();
  const { data: trainings } = useQuery({ queryKey: ["trainings"], queryFn: () => api<Training[]>("/trainings"), staleTime: Infinity });
  const { data: criteria } = useCriteria();
  const [summary, setSummary] = useState(ipr.summary);
  const [goals, setGoals] = useState<IPRGoal[]>(ipr.goals);
  const smart = useMutation({
    mutationFn: () =>
      api<{ model: string; goals: SmartCheck[] }>(`/ipr/${iprId}/ai/smart-check`, {
        method: "POST",
        json: {
          goals: goals.map((g) => ({ goal: g.goal, actions: g.actions, success_measure: g.success_measure, deadline: g.deadline, criterion_id: g.criterion_id })),
        },
      }),
  });

  const save = useMutation({
    mutationFn: (approve: boolean) =>
      api<IPR>(`/ipr/${iprId}`, {
        method: "PATCH",
        json: {
          summary,
          goals: goals.map((g) => ({
            criterion_id: g.criterion_id,
            goal: g.goal,
            actions: g.actions,
            success_measure: g.success_measure,
            deadline: g.deadline,
            training_id: g.training?.id ?? null,
          })),
          status: approve ? "established" : undefined,
        },
      }),
    onSuccess: (r) => {
      qc.setQueryData(["ipr", iprId], r);
      qc.invalidateQueries({ queryKey: ["review", r.review_id] });
    },
  });

  const editable = ipr.can_edit ?? (ipr.status === "draft" && me?.role !== "employee" && me?.employee_id !== ipr.employee.id);
  const step = useMutation({
    mutationFn: (action: "accept" | "approve") => api<IPR>(`/ipr/${iprId}/${action}`, { method: "POST" }),
    onSuccess: (r) => {
      qc.setQueryData(["ipr", iprId], r);
      qc.invalidateQueries({ queryKey: ["reminders"] });
    },
  });
  const upd = (i: number, patch: Partial<IPRGoal>) => setGoals((gs) => gs.map((g, j) => (j === i ? { ...g, ...patch } : g)));

  return (
    <>
      <PageTitle
        title={
          <span className="flex items-center gap-2">
            <GraduationCap className="h-6 w-6 text-primary" aria-hidden /> Indywidualny Program Rozwoju Zawodowego
          </span>
        }
        subtitle={`${ipr.employee.full_name} · ${ipr.employee.position}`}
        action={
          <div className="flex items-center gap-2">
            <Badge tone={ipr.status === "approved" ? "green" : ipr.status === "draft" ? "amber" : "blue"}>{IPR_STATUS[ipr.status]}</Badge>
            {ipr.ai && <AiLabel model={modelLabel(ipr.ai.model)} />}
          </div>
        }
      />
      <div className="space-y-4">
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold">Ścieżka programu (art. 108 ust. 1-2 ustawy o służbie cywilnej)</h2>
          <ol className="grid gap-2 text-sm sm:grid-cols-3">
            {(
              [
                ["Ustala bezpośredni przełożony", ipr.established_at, ["established", "accepted", "approved"]],
                ["Akceptuje kierujący komórką organizacyjną", ipr.accepted_at, ["accepted", "approved"]],
                ["Zatwierdza dyrektor generalny urzędu", ipr.approved_at, ["approved"]],
              ] as const
            ).map(([label, when, done], i) => (
              <li key={label} className={`rounded-md border px-3 py-2 ${(done as readonly string[]).includes(ipr.status) ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-dashed border-border text-slate-500"}`}>
                <div className="text-xs">krok {i + 1}</div>
                <div className="font-medium">{label}</div>
                {when && <div className="text-xs">{fmtDate(when)}</div>}
              </li>
            ))}
          </ol>
          {(ipr.can_accept || ipr.can_approve) && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {ipr.can_accept && (
                <Button onClick={() => step.mutate("accept")} loading={step.isPending}>
                  <CheckCircle2 className="h-4 w-4" aria-hidden /> Akceptuję program
                </Button>
              )}
              {ipr.can_approve && (
                <Button onClick={() => step.mutate("approve")} loading={step.isPending}>
                  <CheckCircle2 className="h-4 w-4" aria-hidden /> Zatwierdzam program
                </Button>
              )}
            </div>
          )}
          <ErrorBox error={step.error} />
        </Card>
        <Card className="space-y-4 p-5">
          <LearningMix actions={goals.map((g) => g.actions)} />
          {ipr.can_edit && (
            <div className="border-t border-border pt-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="ai" size="sm" onClick={() => smart.mutate()} loading={smart.isPending} disabled={!goals.length}>
                  <PenLine className="h-4 w-4" aria-hidden /> Sprawdź cele SMART
                </Button>
                <span className="text-xs text-muted">Konkretny, Mierzalny, Osiągalny, Istotny, określony w Czasie - wynik przy każdym celu.</span>
              </div>
              <AiWaiting active={smart.isPending} typical="20–60 s" />
              <ErrorBox error={smart.error} />
            </div>
          )}
        </Card>
        <Card className="p-5">
          <Label htmlFor="summary">Kierunki rozwoju zawodowego</Label>
          <Textarea id="summary" rows={3} readOnly={!editable} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Card>
        {goals.map((g, i) => (
          <Card key={i} className="space-y-3 p-5">
            {smart.data?.goals[i] && (
              <SmartResult
                check={smart.data.goals[i]}
                model={modelLabel(smart.data.model)}
                goal={g.goal}
                measure={g.success_measure}
                editable={editable}
                onApply={(patch) => upd(i, patch)}
              />
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white">{i + 1}</span>
                {editable ? (
                  <select
                    className="rounded-md border border-border px-2 py-1 text-sm"
                    value={g.criterion_id ?? ""}
                    onChange={(e) => upd(i, { criterion_id: e.target.value ? Number(e.target.value) : null })}
                    aria-label="Kryterium"
                  >
                    <option value="">(bez kryterium)</option>
                    {criteria?.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Badge tone="blue">{g.criterion_name ?? "cel ogólny"}</Badge>
                )}
              </div>
              {editable && (
                <Button size="sm" variant="danger" onClick={() => setGoals(goals.filter((_, j) => j !== i))}>
                  <Trash2 className="h-4 w-4" aria-hidden /> Usuń cel
                </Button>
              )}
            </div>
            <div>
              <Label>Cel rozwojowy</Label>
              <Textarea rows={2} readOnly={!editable} value={g.goal} onChange={(e) => upd(i, { goal: e.target.value })} />
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <Label>Działania</Label>
                  <MixTags actions={g.actions} />
                </div>
                <Textarea rows={3} readOnly={!editable} value={g.actions} onChange={(e) => upd(i, { actions: e.target.value })} />
              </div>
              <div>
                <Label>Miernik sukcesu</Label>
                <Textarea rows={3} readOnly={!editable} value={g.success_measure} onChange={(e) => upd(i, { success_measure: e.target.value })} />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <Label>Termin</Label>
                <Input type="date" readOnly={!editable} value={g.deadline ?? ""} onChange={(e) => upd(i, { deadline: e.target.value || null })} />
              </div>
              <div>
                <Label>Szkolenie z katalogu</Label>
                {editable ? (
                  <select
                    className="w-full rounded-md border border-border px-3 py-2 text-sm"
                    value={g.training?.id ?? ""}
                    onChange={(e) => upd(i, { training: trainings?.find((t) => t.id === Number(e.target.value)) ?? null })}
                  >
                    <option value="">(brak)</option>
                    {trainings?.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} · {t.title} ({t.hours} h)
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="text-sm">{g.training ? `${g.training.title} (${g.training.hours} h, ${g.training.format})` : "—"}</p>
                )}
              </div>
            </div>
          </Card>
        ))}
        {editable && (
          <>
            <Button
              variant="secondary"
              onClick={() => setGoals([...goals, { criterion_id: null, goal: "", actions: "", success_measure: "", deadline: null, training: null }])}
            >
              <Plus className="h-4 w-4" aria-hidden /> Dodaj cel
            </Button>
            <ErrorBox error={save.error} />
            <div className="flex flex-wrap gap-2 border-t border-border pt-4">
              <Button variant="secondary" onClick={() => save.mutate(false)} loading={save.isPending}>
                Zapisz projekt
              </Button>
              <Button onClick={() => save.mutate(true)} loading={save.isPending}>
                <CheckCircle2 className="h-4 w-4" aria-hidden /> Ustal IPRZ i wpisz wnioski do arkusza
              </Button>
            </div>
          </>
        )}
        <Link href={`/reviews/${ipr.review_id}`} className="inline-block text-sm text-primary hover:underline">
          ← wróć do oceny
        </Link>
      </div>
    </>
  );
}
