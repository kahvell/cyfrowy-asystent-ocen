"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarPlus, CheckCircle2, FileSignature, Gavel, Printer, Scale, ShieldCheck, Stamp, Undo2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useCriteria } from "@/components/notes";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Label, Textarea } from "@/components/ui";
import { api, ApiError, getToken } from "@/lib/api";
import type { Review, Warning } from "@/lib/types";
import { cn, daysTo, fmtDate, SCALE } from "@/lib/utils";

const today = () => new Date().toISOString().slice(0, 10);

// ------------------------------------------------------------------ wspólne

export function useReviewMutation(reviewId: number, onWarnings?: (w: Warning[]) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, method = "POST", json }: { path: string; method?: string; json?: unknown }) =>
      api<Review>(`/reviews/${reviewId}${path}`, { method, json }),
    onSuccess: (r) => {
      qc.setQueryData(["review", reviewId], r);
      qc.invalidateQueries({ queryKey: ["team"] });
      qc.invalidateQueries({ queryKey: ["reminders"] });
    },
    onError: (e) => {
      if (onWarnings && e instanceof ApiError && e.warnings.length) onWarnings(e.warnings);
    },
  });
}

const STEPS: { key: Review["status"]; label: string }[] = [
  { key: "criteria", label: "Kryteria i rozmowa rozpoczynająca" },
  { key: "observation", label: "Okres oceny" },
  { key: "draft", label: "Przygotowanie oceny" },
  { key: "submitted", label: "Rozmowa oceniająca" },
  { key: "discussed", label: "Ocena na piśmie" },
  { key: "final", label: "Zapoznanie" },
  { key: "acknowledged", label: "Zakończona" },
];

export function ProcessStepper({ review }: { review: Review }) {
  const status = review.status === "objection" ? "final" : review.status;
  const idx = STEPS.findIndex((s) => s.key === status);
  return (
    <nav aria-label="Etapy oceny okresowej" className="mb-4">
      <ol className="flex flex-wrap gap-1.5 text-xs">
        {STEPS.map((s, i) => (
          <li
            key={s.key}
            aria-current={i === idx ? "step" : undefined}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1",
              i < idx || review.status === "acknowledged" ? "bg-emerald-50 text-emerald-800" : i === idx ? "bg-primary text-white" : "bg-slate-100 text-slate-500",
            )}
          >
            {(i < idx || (review.status === "acknowledged" && i === idx)) && <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />}
            {i + 1}. {s.label}
          </li>
        ))}
        {review.status === "objection" && (
          <li className="flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-red-800">
            <Gavel className="h-3.5 w-3.5" aria-hidden /> sprzeciw w toku
          </li>
        )}
        {review.attempt > 1 && <li className="rounded-full bg-amber-100 px-3 py-1 text-amber-900">ocena sporządzana po raz {review.attempt}.</li>}
      </ol>
    </nav>
  );
}

function DeadlineChip({ label, date, warnDays = 14 }: { label: string; date: string | null; warnDays?: number }) {
  if (!date) return null;
  const d = daysTo(date);
  const tone = d === null ? "slate" : d < 0 ? "red" : d <= warnDays ? "amber" : "slate";
  return (
    <Badge tone={tone}>
      <CalendarClock className="h-3 w-3" aria-hidden /> {label}: {fmtDate(date)}
      {d !== null && d >= 0 && d <= 60 ? ` (${d} dni)` : d !== null && d < 0 ? " (po terminie)" : ""}
    </Badge>
  );
}

export function DeadlinesBar({ review }: { review: Review }) {
  const d = review.deadlines;
  return (
    <div className="mb-6 flex flex-wrap items-center gap-2 text-xs">
      {review.status === "criteria" && <DeadlineChip label="wyznaczenie kryteriów do" date={d.criteria_deadline} />}
      {!["final", "acknowledged", "objection"].includes(review.status) && <DeadlineChip label="termin sporządzenia oceny" date={d.due_date} warnDays={60} />}
      {d.objection_open && <DeadlineChip label="sprzeciw do" date={d.objection_deadline} />}
      {d.repeat_review_date && <DeadlineChip label="ponowna ocena (art. 81 ust. 9)" date={d.repeat_review_date} warnDays={60} />}
      {d.obligatory_promotion && (
        <Badge tone="green">
          <Stamp className="h-3 w-3" aria-hidden /> obligatoryjny kolejny stopień służbowy (art. 89 ust. 2)
          {d.promotion_deadline ? ` do ${fmtDate(d.promotion_deadline)}` : ""}
        </Badge>
      )}
      <Link href={`/reviews/${review.id}/print`} className="ml-auto">
        <Button size="sm" variant="secondary">
          <Printer className="h-4 w-4" aria-hidden /> Arkusz {review.sheet_type} do druku / PDF
        </Button>
      </Link>
    </div>
  );
}

// ------------------------------------------------------------------ Etap I: kryteria

export function CriteriaStage({ review, isReviewer, isEmployee, onWarnings }: { review: Review; isReviewer: boolean; isEmployee: boolean; onWarnings: (w: Warning[]) => void }) {
  const m = useReviewMutation(review.id, onWarnings);
  const { data: allCriteria } = useCriteria();
  const [notes, setNotes] = useState(review.opening_notes);
  const [place, setPlace] = useState(review.criteria_reviewer_place || review.office.city);
  const confirmed = !!review.criteria_reviewer_confirmed_at;
  const editable = isReviewer && !confirmed;
  const mandatory = review.criteria.filter((c) => !c.is_additional);
  const additional = review.criteria.filter((c) => c.is_additional).map((c) => c.criterion_id);
  const options = (allCriteria ?? []).filter((c) => !c.mandatory_for.includes(review.sheet_type));
  const slots = [0, 1, 2].map((i) => additional[i] ?? null);

  const setSlot = (i: number, value: number | null) => {
    const next: (number | null)[] = [...slots];
    next[i] = value;
    m.mutate({ path: "", method: "PATCH", json: { additional_criterion_ids: next.filter((x): x is number => x !== null) } });
  };

  return (
    <Card>
      <CardHeader
        title="Część I arkusza: kryteria oceny i termin sporządzenia oceny"
        subtitle="§ 5 rozporządzenia: rozmowa rozpoczynająca ocenę - obowiązki z opisu stanowiska, kryteria, oczekiwania i cele."
      />
      <div className="grid gap-6 p-5 md:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold">Kryteria obowiązkowe (arkusz {review.sheet_type})</h3>
          <ul className="space-y-1 text-sm">
            {mandatory.map((c) => (
              <li key={c.criterion_id} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden /> {c.name}
              </li>
            ))}
          </ul>
          <h3 className="mb-2 mt-5 text-sm font-semibold">Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3)</h3>
          <div className="space-y-2">
            {slots.map((value, i) => (
              <select
                key={i}
                aria-label={`Kryterium dodatkowe ${i + 1}`}
                disabled={!editable || m.isPending}
                value={value ?? ""}
                onChange={(e) => setSlot(i, e.target.value ? Number(e.target.value) : null)}
                className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm disabled:bg-slate-50"
              >
                <option value="">{editable ? "- wybierz albo pozostaw puste -" : "brak"}</option>
                {options
                  .filter((c) => c.id === value || !slots.includes(c.id))
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            ))}
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <Label htmlFor="due">Termin sporządzenia oceny</Label>
            <Input
              id="due"
              type="date"
              disabled={!editable}
              defaultValue={review.deadlines.due_date ?? ""}
              onBlur={(e) => e.target.value && e.target.value !== review.deadlines.due_date && m.mutate({ path: "", method: "PATCH", json: { due_date: e.target.value } })}
            />
            <p className="mt-1 text-xs text-muted">Wyliczony: 24 miesiące od początku okresu oceny ({fmtDate(review.period_start)}), z przesunięciem na dzień roboczy i o długie nieobecności.</p>
          </div>
          <div>
            <Label htmlFor="opening">Data rozmowy rozpoczynającej</Label>
            <Input
              id="opening"
              type="date"
              disabled={!editable}
              defaultValue={review.opening_conversation_date ?? ""}
              onBlur={(e) => e.target.value !== (review.opening_conversation_date ?? "") && m.mutate({ path: "", method: "PATCH", json: { opening_conversation_date: e.target.value || null } })}
            />
          </div>
          <div>
            <Label htmlFor="opening-notes">Ustalenia z rozmowy: oczekiwania i cele na okres oceny</Label>
            <Textarea
              id="opening-notes"
              rows={4}
              readOnly={!editable}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => notes !== review.opening_notes && m.mutate({ path: "", method: "PATCH", json: { opening_notes: notes } })}
              placeholder="Główne obowiązki, oczekiwania co do sposobu spełniania kryteriów, cele i sposób ich realizacji…"
            />
          </div>
        </div>
      </div>
      <div className="border-t border-border bg-slate-50 px-5 py-4 text-sm">
        <p className="mb-3 text-slate-700">
          Potwierdzamy przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 rozporządzenia, omówienie wszystkich wymaganych zagadnień oraz zapoznanie ocenianego z
          kryteriami oceny i terminem sporządzenia oceny.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Signature who="Oceniający" name={review.reviewer.full_name} place={review.criteria_reviewer_place} date={review.criteria_reviewer_confirmed_at} />
          <Signature who="Oceniany" name={review.employee.full_name} place={review.criteria_employee_place} date={review.criteria_employee_confirmed_at} />
        </div>
        {isReviewer && !confirmed && (
          <div className="mt-3">
            <InviteButton reviewId={review.id} kind="opening" label="Zaproś na rozmowę rozpoczynającą" />
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {isReviewer && !confirmed && (
            <>
              <Input value={place} onChange={(e) => setPlace(e.target.value)} className="w-48" aria-label="Miejscowość" placeholder="miejscowość" />
              <Button onClick={() => m.mutate({ path: "/criteria/confirm", json: { place } })} loading={m.isPending}>
                <FileSignature className="h-4 w-4" aria-hidden /> Potwierdzam rozmowę i wyznaczenie kryteriów
              </Button>
            </>
          )}
          {isReviewer && confirmed && <p className="text-muted">Czeka na potwierdzenie przez ocenianego. Kryteria są zablokowane (zmiana tylko w trybie korekty przez administratora).</p>}
          {isEmployee && confirmed && (
            <Button onClick={() => m.mutate({ path: "/criteria/acknowledge", json: { place: review.criteria_reviewer_place } })} loading={m.isPending}>
              <FileSignature className="h-4 w-4" aria-hidden /> Potwierdzam rozmowę i zapoznanie z kryteriami
            </Button>
          )}
          {isEmployee && !confirmed && <p className="text-muted">Przełożony przygotowuje kryteria. Potwierdzisz je po rozmowie rozpoczynającej.</p>}
        </div>
        <ErrorBox error={m.error} />
      </div>
    </Card>
  );
}

function Signature({ who, name, place, date }: { who: string; name: string; place: string; date: string | null }) {
  return (
    <div className={cn("rounded-md border px-3 py-2", date ? "border-emerald-200 bg-emerald-50" : "border-dashed border-border bg-white")}>
      <div className="text-xs text-muted">{who}</div>
      {date ? (
        <div className="flex items-center gap-1.5 font-medium text-emerald-900">
          <ShieldCheck className="h-4 w-4" aria-hidden /> {name} · {place} · {fmtDate(date)}
        </div>
      ) : (
        <div className="text-slate-500">oczekuje na potwierdzenie</div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ okres oceny

const DUE_REASONS: [string, string][] = [
  ["zmiana_oceniajacego", "zmiana na stanowisku oceniającego (art. 81 ust. 8 pkt 1)"],
  ["nieobecnosc_ocenianego", "przewidywana dłuższa nieobecność ocenianego (pkt 2)"],
  ["nieobecnosc_oceniajacego", "przewidywana dłuższa nieobecność oceniającego (pkt 3)"],
  ["wniosek_ocenianego", "wniosek ocenianego (pkt 4)"],
  ["dluga_nieobecnosc", "nieobecność usprawiedliwiona > 1 mies. (art. 81 ust. 7)"],
];

export function DueDateChange({ review }: { review: Review }) {
  const m = useReviewMutation(review.id);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(review.deadlines.due_date ?? today());
  const [reason, setReason] = useState(DUE_REASONS[0][0]);
  const [note, setNote] = useState("");
  return (
    <div>
      <Button size="sm" variant="secondary" onClick={() => setOpen(!open)}>
        <CalendarClock className="h-4 w-4" aria-hidden /> Zmień termin oceny
      </Button>
      {open && (
        <div className="mt-3 space-y-2 rounded-md border border-border p-3 text-sm">
          {!review.deadlines.can_change_due_date && <p className="text-amber-800">Zmiana terminu (art. 81 ust. 8) jest możliwa po 6 miesiącach od początku okresu oceny.</p>}
          <div className="flex flex-wrap gap-2">
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-auto" aria-label="Nowy termin" />
            <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Powód zmiany" className="rounded-md border border-border px-2 py-1.5 text-sm">
              {DUE_REASONS.map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="uwagi (np. okres nieobecności)" aria-label="Uwagi" />
          <Button size="sm" onClick={() => m.mutate({ path: "/due-date", json: { due_date: date, reason, note } }, { onSuccess: () => setOpen(false) })} loading={m.isPending}>
            Zapisz i powiadom ocenianego
          </Button>
          <ErrorBox error={m.error} />
        </div>
      )}
      {review.due_date_history.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-muted">
          {review.due_date_history.map((h, i) => (
            <li key={i}>
              {fmtDate(h.at)}: termin {h.from ? `${fmtDate(h.from)} → ` : ""}
              {fmtDate(h.date)} · {h.reason}
              {h.note ? ` · ${h.note}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ObservationStage({ review, isReviewer }: { review: Review; isReviewer: boolean }) {
  const m = useReviewMutation(review.id);
  return (
    <Card>
      <CardHeader
        title="Okres oceny: obserwacja pracy i bieżąca informacja zwrotna"
        subtitle={`Od ${fmtDate(review.period_start)} do terminu oceny ${fmtDate(review.deadlines.due_date)}. Kryteria i termin potwierdzone przez obie strony.`}
      />
      <div className="grid gap-6 p-5 md:grid-cols-2">
        <div className="text-sm">
          <h3 className="mb-2 font-semibold">Kryteria oceny</h3>
          <ul className="space-y-1">
            {review.criteria.map((c) => (
              <li key={c.criterion_id}>
                {c.name} {c.is_additional && <Badge tone="blue">dodatkowe</Badge>}
              </li>
            ))}
          </ul>
          {review.opening_notes && (
            <>
              <h3 className="mb-1 mt-4 font-semibold">Ustalenia z rozmowy rozpoczynającej ({fmtDate(review.opening_conversation_date)})</h3>
              <p className="whitespace-pre-line text-slate-700">{review.opening_notes}</p>
            </>
          )}
        </div>
        <div className="space-y-4">
          {isReviewer ? (
            <>
              <p className="text-sm text-slate-600">
                Zapisuj obserwacje w dzienniku na bieżąco. Gdy zbliża się termin, rozpocznij przygotowanie oceny - asystent zbierze notatki z całego okresu.
              </p>
              <div className="flex flex-wrap gap-2">
                <Link href={`/employees/${review.employee.id}`}>
                  <Button variant="secondary">Dziennik obserwacji</Button>
                </Link>
                <Button onClick={() => m.mutate({ path: "/start" })} loading={m.isPending}>
                  <Scale className="h-4 w-4" aria-hidden /> Rozpocznij przygotowanie oceny
                </Button>
              </div>
              <InviteButton reviewId={review.id} kind="feedback" label="Zaproś na rozmowę z informacją zwrotną" />
              <DueDateChange review={review} />
              <DueDateRequests review={review} isReviewer isEmployee={false} />
            </>
          ) : (
            <>
              <p className="text-sm text-slate-600">Trwa okres oceny. Możesz dodawać własne osiągnięcia i wypełnić samoocenę przed rozmową oceniającą.</p>
              <DueDateRequests review={review} isReviewer={false} isEmployee />
            </>
          )}
          <ErrorBox error={m.error} />
        </div>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ część II/III: dane arkusza

export function SheetData({ review, editable }: { review: Review; editable: boolean }) {
  const m = useReviewMutation(review.id);
  const [just, setJust] = useState(review.promotion_justification);
  const patch = (json: Record<string, unknown>) => m.mutate({ path: "", method: "PATCH", json });
  const civil = review.employee.is_civil_servant;
  const positive = review.summary?.result === "pozytywna";

  return (
    <Card>
      <CardHeader title="Pozostałe pola arkusza" subtitle="Uzupełnione automatycznie z bazy - popraw tylko, jeśli dane są niepełne." />
      <div className="space-y-5 p-5 text-sm">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="ps">Okres, w którym oceniany podlegał ocenie: od</Label>
            <Input id="ps" type="date" disabled={!editable} defaultValue={review.period_start} onBlur={(e) => e.target.value !== review.period_start && patch({ period_start: e.target.value })} />
          </div>
          <div>
            <Label htmlFor="pe">do</Label>
            <Input id="pe" type="date" disabled={!editable} defaultValue={review.period_end} onBlur={(e) => e.target.value !== review.period_end && patch({ period_end: e.target.value })} />
          </div>
        </div>

        {civil && (
          <fieldset disabled={!editable}>
            <legend className="mb-2 font-semibold">Dane dotyczące poprzedniej oceny okresowej urzędnika służby cywilnej</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <select aria-label="Ocena poprzednia" value={review.prev_result ?? ""} onChange={(e) => patch({ prev_result: e.target.value || null })} className="rounded-md border border-border px-2 py-1.5">
                <option value="">-</option>
                <option value="pozytywna">pozytywna</option>
                <option value="negatywna">negatywna</option>
                <option value="brak">brak</option>
              </select>
              <select aria-label="Poziom poprzedniej oceny" value={review.prev_level ?? ""} disabled={review.prev_result === "brak"} onChange={(e) => patch({ prev_level: e.target.value || null })} className="rounded-md border border-border px-2 py-1.5">
                <option value="">-</option>
                {SCALE.map((s) => (
                  <option key={s.value} value={s.label}>
                    {s.label}
                  </option>
                ))}
              </select>
              <Input type="date" aria-label="Data sporządzenia poprzedniej oceny" disabled={!editable || review.prev_result === "brak"} defaultValue={review.prev_date ?? ""} onBlur={(e) => e.target.value !== (review.prev_date ?? "") && patch({ prev_date: e.target.value || null })} />
            </div>
          </fieldset>
        )}

        <fieldset disabled={!editable}>
          <legend className="mb-2 font-semibold">Czy do oceny okresowej dołączono wniosek o przyznanie kolejnego stopnia służbowego?</legend>
          <div className="flex flex-wrap gap-4">
            {(
              [
                ["tak", "TAK"],
                ["nie", "NIE"],
                ["nie_dotyczy", "NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)"],
              ] as const
            ).map(([v, l]) => (
              <label key={v} className={cn("flex items-center gap-1.5", ((v === "nie_dotyczy") === civil || (v === "tak" && !positive)) && "opacity-50")}>
                <input
                  type="radio"
                  name="promotion"
                  checked={review.promotion_request === v}
                  disabled={(v === "nie_dotyczy") === civil || (v === "tak" && !positive)}
                  onChange={() => patch({ promotion_request: v })}
                />
                {l}
              </label>
            ))}
          </div>
          {civil && !positive && <p className="mt-1 text-xs text-muted">Wniosek można dołączyć tylko do oceny pozytywnej (art. 89 ust. 1).</p>}
          {review.deadlines.obligatory_promotion && (
            <p className="mt-2 rounded-md bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
              Druga z kolei ocena na jednym z dwóch najwyższych poziomów: urzędnik otrzyma kolejny stopień z mocy prawa (art. 89 ust. 2), niezależnie od wniosku.
            </p>
          )}
        </fieldset>

        {review.promotion_request === "tak" && (
          <fieldset disabled={!editable} className="space-y-3 rounded-md border border-border p-4">
            <legend className="px-1 font-semibold">Część III: wniosek o przyznanie kolejnego stopnia służbowego (art. 89 ust. 1)</legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <Label htmlFor="ay">Rok mianowania</Label>
                <select id="ay" value={review.appointment_year ?? ""} onChange={(e) => patch({ appointment_year: Number(e.target.value) || null })} className="w-full rounded-md border border-border px-2 py-1.5">
                  <option value="">-</option>
                  {Array.from({ length: new Date().getFullYear() - 2007 }, (_, i) => 2008 + i).map((y) => (
                    <option key={y}>{y}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="cg">Posiadany stopień służbowy</Label>
                <select id="cg" value={review.civil_grade ?? ""} onChange={(e) => patch({ civil_grade: Number(e.target.value) || null })} className="w-full rounded-md border border-border px-2 py-1.5">
                  <option value="">-</option>
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => (
                    <option key={g} value={g}>
                      {g}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="cgd">Data przyznania stopnia</Label>
                <Input id="cgd" type="date" defaultValue={review.civil_grade_date ?? ""} onBlur={(e) => patch({ civil_grade_date: e.target.value || null })} />
              </div>
            </div>
            {review.promotion_target && (
              <p>
                Wnioskuję o przyznanie <strong>{review.promotion_target}</strong> stopnia służbowego.
              </p>
            )}
            <div>
              <Label htmlFor="pj">Umotywowanie wniosku (obowiązkowe)</Label>
              <Textarea id="pj" rows={3} value={just} onChange={(e) => setJust(e.target.value)} onBlur={() => just !== review.promotion_justification && patch({ promotion_justification: just })} />
            </div>
          </fieldset>
        )}
        <ErrorBox error={m.error} />
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ zapoznanie, fikcja, sprzeciw

export function DeliveryPanel({ review, isReviewer, isEmployee, isHr }: { review: Review; isReviewer: boolean; isEmployee: boolean; isHr: boolean }) {
  const m = useReviewMutation(review.id);
  const [fiction, setFiction] = useState("");
  const [objection, setObjection] = useState("");
  const [showFiction, setShowFiction] = useState(false);
  const [showObjection, setShowObjection] = useState(false);
  const d = review.deadlines;

  return (
    <Card>
      <CardHeader title="Podpisy, zapoznanie z oceną i sprzeciw" subtitle="Art. 81 ust. 3 i art. 83 ustawy o służbie cywilnej" />
      <div className="space-y-4 p-5 text-sm">
        <div className="grid gap-3 sm:grid-cols-2">
          <Signature who="Oceniający - sporządzenie oceny" name={review.reviewer.full_name} place={review.reviewer_place} date={review.reviewer_signed_at} />
          <Signature
            who={review.ack_fiction ? "Oceniany - fikcja zapoznania" : "Oceniany - rozmowa i zapoznanie z oceną"}
            name={review.employee.full_name}
            place={review.employee_place}
            date={review.acknowledged_at}
          />
        </div>
        {review.ack_fiction && <p className="rounded-md bg-amber-50 px-3 py-2 text-amber-900">Stwierdzono fikcję zapoznania: {review.ack_fiction_note}</p>}

        {review.status === "final" && isEmployee && (
          <div className="rounded-md border border-primary/30 bg-blue-50 p-4">
            <p className="mb-3">Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami dotyczącymi indywidualnego programu rozwoju zawodowego.</p>
            <Button onClick={() => m.mutate({ path: "/acknowledge", json: { place: review.reviewer_place } })} loading={m.isPending}>
              <FileSignature className="h-4 w-4" aria-hidden /> Potwierdzam zapoznanie z oceną
            </Button>
          </div>
        )}
        {review.status === "final" && isReviewer && (
          <div>
            <p className="text-muted">Ocena przekazana ocenianemu. Czeka na potwierdzenie zapoznania.</p>
            <Button size="sm" variant="ghost" className="mt-2" onClick={() => setShowFiction(!showFiction)}>
              Stwierdź fikcję zapoznania
            </Button>
            {showFiction && (
              <div className="mt-2 space-y-2">
                <Textarea rows={2} value={fiction} onChange={(e) => setFiction(e.target.value)} placeholder="Np. „Informacja o ocenie doręczona 12.06 przez EZD; oceniany odmówił podpisu.”" />
                <Button size="sm" variant="danger" disabled={fiction.trim().length < 5} onClick={() => m.mutate({ path: "/ack-fiction", json: { note: fiction } })} loading={m.isPending}>
                  Potwierdzam doręczenie informacji o ocenie
                </Button>
              </div>
            )}
          </div>
        )}

        <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
          <strong>Pouczenie.</strong> Na podstawie art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej służy, w terminie 7 dni od dnia
          zapoznania się z oceną, sprzeciw do {review.office.objection_body}.
        </p>

        {d.objection_open && isEmployee && (
          <div>
            <Button size="sm" variant="secondary" onClick={() => setShowObjection(!showObjection)}>
              <Gavel className="h-4 w-4" aria-hidden /> Wnieś sprzeciw (do {fmtDate(d.objection_deadline)})
            </Button>
            {showObjection && (
              <div className="mt-2 space-y-2">
                <Textarea rows={3} value={objection} onChange={(e) => setObjection(e.target.value)} placeholder="Uzasadnienie sprzeciwu…" />
                <Button size="sm" disabled={objection.trim().length < 10} onClick={() => m.mutate({ path: "/objection", json: { text: objection } })} loading={m.isPending}>
                  Złóż sprzeciw do {review.office.objection_body}
                </Button>
              </div>
            )}
          </div>
        )}

        {review.objection_at && (
          <div className="rounded-md border border-red-200 bg-red-50 p-4">
            <p className="font-medium text-red-900">Sprzeciw z {fmtDate(review.objection_at)}</p>
            <p className="mt-1 whitespace-pre-line text-red-900">{review.objection_text}</p>
            {review.objection_decision && (
              <p className="mt-2 text-red-900">
                Rozstrzygnięcie ({fmtDate(review.objection_decided_at)}):{" "}
                <strong>
                  {review.objection_decision === "odrzucony" ? "sprzeciw nieuwzględniony" : review.objection_decision === "zmiana" ? "ocena do zmiany" : "ocena do sporządzenia po raz drugi"}
                </strong>
                {review.objection_decision === "odrzucony" && " - oceniany może odwołać się do sądu pracy w 14 dni (art. 83 ust. 5)."}
              </p>
            )}
            {review.status === "objection" && isHr && (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => m.mutate({ path: "/objection/decision", json: { decision: "odrzucony" } })} loading={m.isPending}>
                  Nie uwzględniam
                </Button>
                <Button size="sm" variant="secondary" onClick={() => m.mutate({ path: "/objection/decision", json: { decision: "zmiana" } })} loading={m.isPending}>
                  <Undo2 className="h-4 w-4" aria-hidden /> Uwzględniam - zmiana oceny
                </Button>
                <Button size="sm" variant="secondary" onClick={() => m.mutate({ path: "/objection/decision", json: { decision: "ponowne_sporzadzenie" } })} loading={m.isPending}>
                  Uwzględniam - sporządzenie po raz drugi
                </Button>
              </div>
            )}
          </div>
        )}
        <ErrorBox error={m.error} />
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ integracja: zaproszenie do kalendarza

export function InviteButton({ reviewId, kind, label }: { reviewId: number; kind: "opening" | "assessment" | "feedback"; label: string }) {
  const [when, setWhen] = useState(() => {
    const d = new Date(Date.now() + 2 * 86400000);
    return `${d.toISOString().slice(0, 10)}T10:00`;
  });
  const [err, setErr] = useState<string | null>(null);
  const download = async () => {
    setErr(null);
    const res = await fetch(`/api/reviews/${reviewId}/invite.ics?kind=${kind}&when=${encodeURIComponent(when)}`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!res.ok) return setErr("Nie udało się przygotować zaproszenia");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `rozmowa-${kind}.ics`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="w-auto" aria-label={`Termin: ${label}`} />
      <Button size="sm" variant="secondary" onClick={download}>
        <CalendarPlus className="h-4 w-4" aria-hidden /> {label} (.ics)
      </Button>
      {err && <span className="text-xs text-red-700">{err}</span>}
    </div>
  );
}

// ------------------------------------------------------------------ wniosek ocenianego o zmianę terminu (art. 81 ust. 8 pkt 4)

interface DueRequest {
  id: number;
  proposed_date: string;
  reason: string;
  status: "pending" | "accepted" | "rejected";
  decision_note: string;
  created_at: string;
}

export function DueDateRequests({ review, isReviewer, isEmployee }: { review: Review; isReviewer: boolean; isEmployee: boolean }) {
  const qc = useQueryClient();
  const key = ["due-requests", review.id];
  const { data = [] } = useQuery({ queryKey: key, queryFn: () => api<DueRequest[]>(`/reviews/${review.id}/due-date-requests`) });
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: key });
    qc.invalidateQueries({ queryKey: ["review", review.id] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };
  const create = useMutation({
    mutationFn: () => api(`/reviews/${review.id}/due-date-requests`, { method: "POST", json: { proposed_date: date, reason } }),
    onSuccess: () => {
      setReason("");
      refresh();
    },
  });
  const decide = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) => api(`/due-date-requests/${id}/decision`, { method: "POST", json: { accept, note } }),
    onSuccess: refresh,
  });
  const pending = data.find((r) => r.status === "pending");
  if (!isEmployee && data.length === 0) return null;

  return (
    <div className="space-y-2 rounded-md border border-border p-3 text-sm">
      <h4 className="font-medium">Wniosek o zmianę terminu oceny (art. 81 ust. 8 pkt 4)</h4>
      {data.map((r) => (
        <div key={r.id} className="rounded-md bg-slate-50 px-3 py-2">
          <div>
            Proponowany termin: <strong>{fmtDate(r.proposed_date)}</strong> ·{" "}
            <Badge tone={r.status === "pending" ? "amber" : r.status === "accepted" ? "green" : "red"}>
              {r.status === "pending" ? "czeka na rozpatrzenie" : r.status === "accepted" ? "uwzględniony" : "nieuwzględniony"}
            </Badge>
          </div>
          <div className="text-slate-600">{r.reason}</div>
          {r.decision_note && <div className="text-xs text-muted">Odpowiedź: {r.decision_note}</div>}
          {isReviewer && r.status === "pending" && (
            <div className="mt-2 flex flex-wrap gap-2">
              <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="uwagi (opcjonalnie)" className="w-60" aria-label="Uwagi do decyzji" />
              <Button size="sm" onClick={() => decide.mutate({ id: r.id, accept: true })} loading={decide.isPending}>
                Uwzględnij
              </Button>
              <Button size="sm" variant="secondary" onClick={() => decide.mutate({ id: r.id, accept: false })} loading={decide.isPending}>
                Nie uwzględniaj
              </Button>
            </div>
          )}
        </div>
      ))}
      {isEmployee && !pending && (
        review.deadlines.can_change_due_date ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="w-auto" aria-label="Proponowany termin" />
              <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Uzasadnienie wniosku" className="min-w-60 flex-1" aria-label="Uzasadnienie" />
            </div>
            <Button size="sm" variant="secondary" disabled={!date || reason.trim().length < 5} onClick={() => create.mutate()} loading={create.isPending}>
              Złóż wniosek do oceniającego
            </Button>
          </div>
        ) : (
          <p className="text-xs text-muted">Wniosek można złożyć po upływie 6 miesięcy od początku okresu oceny.</p>
        )
      )}
      <ErrorBox error={create.error || decide.error} />
    </div>
  );
}
