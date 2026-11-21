"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ClipboardCheck, GraduationCap, MessagesSquare, NotebookText, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ComparePanel, DraftSuggestion, SourceChip, WarningsList } from "@/components/ai-panels";
import { ConversationPrep } from "@/components/hr-partner";
import { CriteriaStage, DeadlinesBar, DeliveryPanel, DueDateRequests, InviteButton, ObservationStage, ProcessStepper, SheetData } from "@/components/process";
import { useMe } from "@/components/app-shell";
import { NoteItem } from "@/components/notes";
import { AiWaiting, Badge, Button, Card, CardHeader, ErrorBox, Input, PageTitle, Spinner, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { ComparePayload, DraftPayload, Note, Review, ReviewCriterion, Suggestion, Warning } from "@/lib/types";
import { cn, fmtDate, SCALE, scaleLabel } from "@/lib/utils";

function CriterionCard({
  review,
  c,
  editable,
  onShowNote,
  register,
}: {
  review: Review;
  c: ReviewCriterion;
  editable: boolean;
  onShowNote: (id: number) => void;
  register: (id: number, el: HTMLDivElement | null) => void;
}) {
  const qc = useQueryClient();
  const [text, setText] = useState(c.justification);
  const [open, setOpen] = useState(false);
  const [suggestion, setSuggestion] = useState<Suggestion<DraftPayload> | null>(null);

  const patch = useMutation({
    mutationFn: (body: Partial<{ score: number | null; justification: string }>) =>
      api<Review>(`/reviews/${review.id}`, { method: "PATCH", json: { criteria: [{ criterion_id: c.criterion_id, ...body }] } }),
    onSuccess: (r) => qc.setQueryData(["review", review.id], r),
  });
  const draft = useMutation({
    mutationFn: () => api<Suggestion<DraftPayload>>(`/reviews/${review.id}/ai/draft?criterion_id=${c.criterion_id}`, { method: "POST" }),
    onSuccess: setSuggestion,
  });

  return (
    <Card className="scroll-mt-24 p-5" ref={(el) => register(c.criterion_id, el)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">
            {c.name} {c.is_additional && <Badge tone="blue">dodatkowe</Badge>}
          </h3>
          <button onClick={() => setOpen(!open)} className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground" aria-expanded={open}>
            <ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} aria-hidden /> wskaźniki z rozporządzenia
          </button>
        </div>
        {editable && (
          <Button size="sm" variant="ai" onClick={() => draft.mutate()} loading={draft.isPending}>
            <Sparkles className="h-4 w-4" aria-hidden /> Zaproponuj uzasadnienie
          </Button>
        )}
      </div>
      {open && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-600">
          {c.indicators.map((i) => (
            <li key={i}>{i}</li>
          ))}
        </ul>
      )}
      <fieldset className="mt-3" disabled={!editable}>
        <legend className="sr-only">Ocena cząstkowa</legend>
        <div className="grid grid-cols-5 gap-1.5">
          {SCALE.map((s) => (
            <button
              key={s.value}
              type="button"
              aria-pressed={c.score === s.value}
              title={s.label}
              onClick={() => patch.mutate({ score: c.score === s.value ? null : s.value })}
              className={cn(
                "rounded-md border px-1 py-1.5 text-center text-xs leading-tight transition-colors disabled:cursor-default",
                c.score === s.value ? "border-primary bg-primary text-white" : "border-border bg-white hover:bg-slate-50",
              )}
            >
              <div className="text-base font-semibold">{s.value}</div>
              <div className="hidden sm:block">{s.short}</div>
            </button>
          ))}
        </div>
      </fieldset>
      <div className="mt-3">
        <Textarea
          rows={3}
          value={text}
          readOnly={!editable}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => text !== c.justification && patch.mutate({ justification: text })}
          placeholder="Uzasadnienie: konkretne zachowania i sytuacje z okresu oceny…"
          aria-label={`Uzasadnienie: ${c.name}`}
        />
        {c.source_note_ids.length > 0 && (
          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted">
            Źródła: {c.source_note_ids.map((id) => <SourceChip key={id} id={id} onClick={onShowNote} />)}
          </div>
        )}
      </div>
      <AiWaiting active={draft.isPending} />
      <ErrorBox error={patch.error || draft.error} />
      {suggestion && (
        <DraftSuggestion
          suggestion={suggestion}
          reviewId={review.id}
          onShowNote={onShowNote}
          onApplyScore={(score) => patch.mutate({ score })}
          onClose={() => setSuggestion(null)}
        />
      )}
    </Card>
  );
}

function ReadOnlyReview({ review }: { review: Review }) {
  if (review.status === "draft")
    return (
      <Card className="p-6">
        <p className="text-sm">Przełożony przygotowuje ocenę. Zobaczysz ją przed rozmową oceniającą.</p>
        <Link href={`/reviews/${review.id}/self`} className="mt-3 inline-block">
          <Button>Wypełnij samoocenę</Button>
        </Link>
      </Card>
    );
  if (!review.summary) return null;
  return (
    <div className="space-y-4">
      {review.criteria.map((c) => (
        <Card key={c.criterion_id} className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{c.name}</h3>
            <Badge tone="blue">
              {c.score} pkt · {scaleLabel(c.score)}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-slate-700">{c.justification || "—"}</p>
        </Card>
      ))}
      {review.summary && (
        <Card className="p-5 text-sm">
          Ogólny poziom: <strong>{review.summary.level}</strong> ({review.summary.average} pkt) · ocena{" "}
          <strong>{review.summary.result ?? "w toku"}</strong>
        </Card>
      )}
      {review.ipr_id && (
        <Link href={`/ipr/${review.ipr_id}`}>
          <Button variant="secondary">
            <GraduationCap className="h-4 w-4" aria-hidden /> Mój plan rozwoju (IPR)
          </Button>
        </Link>
      )}
    </div>
  );
}

function OverallJustification({ review, editable }: { review: Review; editable: boolean }) {
  const qc = useQueryClient();
  const [overall, setOverall] = useState(review.justification);
  const save = useMutation({
    mutationFn: () => api<Review>(`/reviews/${review.id}`, { method: "PATCH", json: { justification: overall } }),
    onSuccess: (r) => qc.setQueryData(["review", review.id], r),
  });
  return (
    <div>
      <label htmlFor="overall" className="mb-1 block text-sm font-medium">
        Uzasadnienie przyznanej oceny {review.summary?.result === "negatywna" ? "(obowiązkowe, § 11 ust. 3)" : "(opcjonalne)"}
      </label>
      <Textarea
        id="overall"
        rows={3}
        value={overall}
        readOnly={!editable}
        onChange={(e) => setOverall(e.target.value)}
        onBlur={() => overall !== review.justification && save.mutate()}
      />
      <ErrorBox error={save.error} />
    </div>
  );
}

type Tab = "quality" | "evidence" | "compare" | "prep";

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const reviewId = Number(id);
  const me = useMe();
  const qc = useQueryClient();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("quality");
  const [highlight, setHighlight] = useState<number | null>(null);
  const [warnings, setWarnings] = useState<Warning[] | null>(null);
  const [compare, setCompare] = useState<Suggestion<ComparePayload> | null>(null);
  const [convDate, setConvDate] = useState(() => new Date().toISOString().slice(0, 10));
  const cardRefs = useRef(new Map<number, HTMLDivElement>());

  const { data: review, error, isPending } = useQuery({ queryKey: ["review", reviewId], queryFn: () => api<Review>(`/reviews/${reviewId}`) });
  const isReviewer = !!review && (me?.role === "manager" || me?.role === "admin") && me?.employee_id !== review.employee.id;
  const isEmployee = !!review && me?.employee_id === review.employee.id;
  const isHr = me?.role === "hr" || me?.role === "admin";
  const { data: evidence } = useQuery({
    queryKey: ["evidence", reviewId],
    queryFn: () => api<Note[]>(`/reviews/${reviewId}/evidence`),
    enabled: isReviewer && !["criteria", "observation"].includes(review?.status ?? ""),
  });

  const quality = useMutation({
    mutationFn: () => api<{ warnings: Warning[] }>(`/reviews/${reviewId}/ai/quality-check`, { method: "POST" }),
    onSuccess: (r) => {
      setWarnings(r.warnings);
      setTab("quality");
    },
  });
  const cmp = useMutation({
    mutationFn: () => api<Suggestion<ComparePayload>>(`/reviews/${reviewId}/ai/compare-self`, { method: "POST" }),
    onSuccess: (s) => {
      setCompare(s);
      setTab("compare");
    },
  });
  const transition = useMutation({
    mutationFn: ({ action, json }: { action: string; json?: unknown }) => api<Review>(`/reviews/${reviewId}/${action}`, { method: "POST", json }),
    onSuccess: (r) => {
      qc.setQueryData(["review", reviewId], r);
      qc.invalidateQueries({ queryKey: ["team"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.warnings.length) {
        setWarnings(e.warnings);
        setTab("quality");
      }
    },
  });
  const genIpr = useMutation({
    mutationFn: () => api<{ id: number }>(`/reviews/${reviewId}/ipr/generate`, { method: "POST" }),
    onSuccess: (ipr) => {
      qc.invalidateQueries({ queryKey: ["review", reviewId] });
      router.push(`/ipr/${ipr.id}`);
    },
  });

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const editable = isReviewer && (review.status === "draft" || review.status === "discussed");
  const showNote = (nid: number) => {
    setTab("evidence");
    setHighlight(nid);
    setTimeout(() => document.getElementById(`note-${nid}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  const jump = (cid: number) => cardRefs.current.get(cid)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <>
      <PageTitle
        title={
          <>
            Arkusz oceny {review.sheet_type}: {review.employee.full_name}
          </>
        }
        subtitle={`${review.employee.position} · okres oceny ${fmtDate(review.period_start)} – ${fmtDate(review.period_end)} · oceniający: ${review.reviewer.full_name}`}
        action={
          isReviewer && (
            <Link href={`/employees/${review.employee.id}`} className="text-sm text-primary hover:underline">
              ← dziennik pracownika
            </Link>
          )
        }
      />
      <ProcessStepper review={review} />
      <DeadlinesBar review={review} />

      {review.status === "criteria" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <CriteriaStage review={review} isReviewer={isReviewer} isEmployee={isEmployee} onWarnings={setWarnings} />
          <aside className="space-y-4">
            {warnings && <WarningsList warnings={warnings} review={review} onShowNote={() => {}} onJump={() => {}} />}
            {isReviewer && <ConversationPrep reviewId={review.id} kind="opening" />}
          </aside>
        </div>
      ) : review.status === "observation" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <ObservationStage review={review} isReviewer={isReviewer} />
          {isReviewer && (
            <aside>
              <ConversationPrep reviewId={review.id} kind="feedback" />
            </aside>
          )}
        </div>
      ) : !isReviewer ? (
        <div className="space-y-6">
          <ReadOnlyReview review={review} />
          {isEmployee && ["draft", "submitted"].includes(review.status) && <DueDateRequests review={review} isReviewer={false} isEmployee />}
          {["final", "acknowledged", "objection"].includes(review.status) && <DeliveryPanel review={review} isReviewer={false} isEmployee={isEmployee} isHr={isHr} />}
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-4">
            {review.criteria.map((c) => (
              <CriterionCard
                key={`${c.criterion_id}:${c.justification}`}
                review={review}
                c={c}
                editable={editable}
                onShowNote={showNote}
                register={(cid, el) => (el ? cardRefs.current.set(cid, el) : cardRefs.current.delete(cid))}
              />
            ))}

            <Card>
              <CardHeader title="Przyznanie oceny (§ 11)" subtitle="Liczone automatycznie wg skali z rozporządzenia" />
              <div className="space-y-4 p-5">
                {review.summary ? (
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <span>
                      Średnia: <strong>{review.summary.average.toFixed(2)} pkt</strong>
                    </span>
                    <span>
                      Ogólny poziom: <strong>{review.summary.level}</strong>
                    </span>
                    {review.summary.result ? (
                      <Badge tone={review.summary.result === "pozytywna" ? "green" : "red"}>ocena {review.summary.result}</Badge>
                    ) : (
                      <Badge tone="amber">uzupełnij wszystkie kryteria</Badge>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-muted">Wystaw oceny cząstkowe.</p>
                )}
                <OverallJustification key={review.justification} review={review} editable={editable} />
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium">Wnioski dotyczące IPR (§ 11 ust. 1 pkt 5)</span>
                    {review.ipr_id ? (
                      <Link href={`/ipr/${review.ipr_id}`} className="text-sm text-primary hover:underline">
                        otwórz IPR →
                      </Link>
                    ) : (
                      <Button size="sm" variant="ai" onClick={() => genIpr.mutate()} loading={genIpr.isPending} disabled={!review.summary}>
                        <GraduationCap className="h-4 w-4" aria-hidden /> Zaproponuj IPR
                      </Button>
                    )}
                  </div>
                  <p className="whitespace-pre-line rounded-md bg-slate-50 p-3 text-sm text-slate-700">
                    {review.ipr_conclusions || "Pojawią się po zatwierdzeniu IPR."}
                  </p>
                  <AiWaiting active={genIpr.isPending} typical="60–120 s" />
                  <ErrorBox error={genIpr.error} />
                </div>
              </div>
            </Card>

            {["draft", "submitted"].includes(review.status) && <DueDateRequests review={review} isReviewer isEmployee={false} />}
            <SheetData key={`${review.updated_at}`} review={review} editable={editable} />

            {["final", "acknowledged", "objection"].includes(review.status) && (
              <DeliveryPanel review={review} isReviewer={isReviewer} isEmployee={false} isHr={isHr} />
            )}

            <Card className="p-5">
              <div className="flex flex-wrap items-center gap-2">
                {review.status === "draft" && (
                  <Button onClick={() => transition.mutate({ action: "submit" })} loading={transition.isPending}>
                    <ClipboardCheck className="h-4 w-4" aria-hidden /> Przekaż do rozmowy oceniającej
                  </Button>
                )}
                {review.status === "submitted" && (
                  <>
                    <div className="w-full">
                      <InviteButton reviewId={review.id} kind="assessment" label="Zaproś na rozmowę oceniającą" />
                    </div>
                    <Input type="date" value={convDate} onChange={(e) => setConvDate(e.target.value)} className="w-auto" aria-label="Data rozmowy" />
                    <Button onClick={() => transition.mutate({ action: "discussed", json: { conversation_date: convDate } })} loading={transition.isPending}>
                      <MessagesSquare className="h-4 w-4" aria-hidden /> Rozmowa przeprowadzona
                    </Button>
                    <Button variant="ghost" onClick={() => transition.mutate({ action: "reopen" })}>
                      Wróć do szkicu
                    </Button>
                  </>
                )}
                {review.status === "discussed" && (
                  <Button onClick={() => transition.mutate({ action: "finalize", json: { place: review.reviewer_place || review.office.city } })} loading={transition.isPending}>
                    <CheckCircle2 className="h-4 w-4" aria-hidden /> Sporządź ocenę na piśmie i przekaż ocenianemu
                  </Button>
                )}
                {review.status === "final" && <p className="text-sm text-amber-800">Ocena przekazana ocenianemu - czeka na potwierdzenie zapoznania.</p>}
                {review.status === "acknowledged" && (
                  <p className="text-sm text-emerald-800">
                    Proces zakończony. Oceniany zapoznał się z oceną {fmtDate(review.acknowledged_at)}
                    {review.deadlines.objection_open ? ` - sprzeciw możliwy do ${fmtDate(review.deadlines.objection_deadline)}.` : "."}
                  </p>
                )}
                {review.status === "objection" && <p className="text-sm text-red-800">Sprzeciw rozpatruje {review.office.objection_body} (14 dni, art. 83 ust. 3).</p>}
              </div>
              <ErrorBox error={transition.error} />
            </Card>
          </div>

          {/* Panel asystenta */}
          <aside className="lg:sticky lg:top-4 lg:self-start">
            <Card>
              <div className="flex border-b border-border" role="tablist">
                {(
                  [
                    ["quality", "Kontrola jakości", ShieldAlert],
                    ["evidence", "Dowody", NotebookText],
                    ["compare", "Samoocena", MessagesSquare],
                    ["prep", "Rozmowa", Sparkles],
                  ] as const
                ).map(([key, label, Icon]) => (
                  <button
                    key={key}
                    role="tab"
                    aria-selected={tab === key}
                    onClick={() => setTab(key)}
                    className={cn(
                      "flex flex-1 items-center justify-center gap-1.5 px-3 py-3 text-sm",
                      tab === key ? "border-b-2 border-primary font-medium text-primary" : "text-slate-600 hover:bg-slate-50",
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden /> {label}
                  </button>
                ))}
              </div>
              <div className="max-h-[calc(100vh-10rem)] overflow-y-auto p-4">
                {tab === "quality" && (
                  <div className="space-y-3">
                    <p className="text-sm text-slate-600">
                      Sprawdza efekt świeżości, efekt halo, brak dowodów, niespójność ocen z notatkami, ogólniki i język stronniczy.
                    </p>
                    <Button variant="ai" className="w-full" onClick={() => quality.mutate()} loading={quality.isPending}>
                      <ShieldAlert className="h-4 w-4" aria-hidden /> Sprawdź jakość oceny
                    </Button>
                    <AiWaiting active={quality.isPending} />
                    <ErrorBox error={quality.error} />
                    {warnings && <WarningsList warnings={warnings} review={review} onShowNote={showNote} onJump={jump} />}
                  </div>
                )}
                {tab === "evidence" && (
                  <div>
                    <p className="mb-2 text-sm text-slate-600">Notatki z dziennika z okresu oceny ({evidence?.length ?? 0}).</p>
                    <ul className="-mx-4 divide-y divide-border">
                      {evidence?.map((n) => <NoteItem key={n.id} note={n} highlighted={highlight === n.id} />)}
                    </ul>
                  </div>
                )}
                {tab === "prep" && <ConversationPrep reviewId={review.id} kind="assessment" bare />}
                {tab === "compare" && (
                  <div className="space-y-3">
                    {review.self_assessment_submitted ? (
                      <>
                        <Button variant="ai" className="w-full" onClick={() => cmp.mutate()} loading={cmp.isPending}>
                          <Sparkles className="h-4 w-4" aria-hidden /> Porównaj z samooceną i przygotuj pytania
                        </Button>
                        <AiWaiting active={cmp.isPending} />
                        <ErrorBox error={cmp.error} />
                        {compare && <ComparePanel suggestion={compare} />}
                      </>
                    ) : (
                      <p className="text-sm text-muted">Pracownik nie przekazał jeszcze samooceny.</p>
                    )}
                  </div>
                )}
              </div>
            </Card>
            <p className="mt-3 flex items-start gap-1.5 px-1 text-xs text-muted">
              <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-ai" aria-hidden />
              AI tylko proponuje: każda propozycja wskazuje notatki źródłowe, a decyzja (akceptacja, edycja, odrzucenie) jest zapisywana w dzienniku
              zdarzeń. Ocen cząstkowych AI nie wystawia.
            </p>
          </aside>
        </div>
      )}
    </>
  );
}
