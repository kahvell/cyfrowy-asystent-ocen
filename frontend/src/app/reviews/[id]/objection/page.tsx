"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gavel } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useMe } from "@/components/app-shell";
import { Badge, Button, Card, CardHeader, ErrorBox, PageTitle, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { Review } from "@/lib/types";
import { fmtDate } from "@/lib/utils";

const DECISION_LABEL: Record<NonNullable<Review["objection_decision"]>, string> = {
  odrzucony: "sprzeciw nieuwzględniony",
  zmiana: "ocena do zmiany",
  ponowne_sporzadzenie: "ocena do sporządzenia po raz drugi",
};

/** Strona sprzeciwu od oceny okresowej (art. 83 ustawy o służbie cywilnej) - dostępna dla ocenianego
 * na etapie zapoznania („nie akceptuję”) oraz w terminie 7 dni od zapoznania się z oceną. */
export default function ObjectionPage() {
  const { id } = useParams<{ id: string }>();
  const reviewId = Number(id);
  const me = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const [text, setText] = useState("");

  const { data: review, error, isPending } = useQuery({
    queryKey: ["review", reviewId],
    queryFn: () => api<Review>(`/reviews/${reviewId}`),
  });

  const submit = useMutation({
    mutationFn: () => api<Review>(`/reviews/${reviewId}/objection`, { method: "POST", json: { text } }),
    onSuccess: (r) => {
      qc.setQueryData(["review", reviewId], r);
      qc.invalidateQueries({ queryKey: ["team"] });
      router.push(`/reviews/${reviewId}`);
    },
  });

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const isEmployee = me?.employee_id === review.employee.id;
  // z etapu zapoznania (status „final”) sprzeciw można wnieść od razu; po zapoznaniu obowiązuje okno 7 dni
  const canFile = isEmployee && (review.status === "final" || (review.status === "acknowledged" && review.deadlines.objection_open));

  return (
    <>
      <PageTitle
        title="Sprzeciw od oceny okresowej"
        subtitle={`${review.employee.full_name} · arkusz ${review.sheet_type} · oceniający: ${review.reviewer.full_name}`}
        action={
          <Link href={`/reviews/${reviewId}`} className="text-sm text-primary hover:underline">
            ← wróć do arkusza oceny
          </Link>
        }
      />

      <p className="mb-4 rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
        <strong>Pouczenie.</strong> Na podstawie art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny
        okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do {review.office.objection_body}. Sprzeciw
        rozpatruje się w terminie 14 dni od dnia wniesienia (art. 83 ust. 3).
      </p>

      {!isEmployee ? (
        <Card className="p-6 text-sm">
          <p>Sprzeciw wnosi oceniany pracownik. Ta strona jest dostępna wyłącznie dla ocenianego.</p>
        </Card>
      ) : review.status === "objection" ? (
        <Card className="p-6 text-sm">
          <p className="font-medium text-red-900">Sprzeciw wniesiono {fmtDate(review.objection_at)}.</p>
          <p className="mt-1 whitespace-pre-line text-red-900">{review.objection_text}</p>
          {review.objection_decision && (
            <p className="mt-2 text-red-900">
              Rozstrzygnięcie ({fmtDate(review.objection_decided_at)}): <strong>{DECISION_LABEL[review.objection_decision]}</strong>
              {review.objection_decision === "odrzucony" && " - możesz odwołać się do sądu pracy w terminie 14 dni (art. 83 ust. 5)."}
            </p>
          )}
        </Card>
      ) : canFile ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            <CardHeader title="Treść sprzeciwu" subtitle="Wskaż, którym elementom oceny i dlaczego nie zgadzasz się, wraz z uzasadnieniem." />
            <div className="space-y-3 p-5">
              <Textarea
                rows={8}
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={submit.isPending}
                placeholder="Nie zgadzam się z oceną w zakresie… Uzasadnienie: …"
                aria-label="Treść sprzeciwu"
              />
              <p className="text-xs text-muted">Wymagane min. 10 znaków.</p>
              <ErrorBox error={submit.error} />
              <div className="flex flex-wrap gap-2">
                <Button disabled={text.trim().length < 10} loading={submit.isPending} onClick={() => submit.mutate()}>
                  <Gavel className="h-4 w-4" aria-hidden /> Wnieś sprzeciw do {review.office.objection_body}
                </Button>
                <Link href={`/reviews/${reviewId}`}>
                  <Button variant="ghost">Anuluj</Button>
                </Link>
              </div>
            </div>
          </Card>

          <aside className="space-y-4">
            <Card className="p-5 text-sm">
              <h3 className="mb-2 font-semibold">Termin</h3>
              {review.deadlines.objection_deadline ? (
                <p>
                  Sprzeciw możesz wnieść do <strong>{fmtDate(review.deadlines.objection_deadline)}</strong>. Termin biegnie od dnia
                  zapoznania się z oceną; jeśli koniec wypada w dzień wolny, przesuwa się na najbliższy dzień roboczy.
                </p>
              ) : (
                <p>Termin 7 dni liczy się od dnia zapoznania się z oceną. Wniesienie sprzeciwu oznacza zapoznanie się z oceną.</p>
              )}
            </Card>
            <Card className="p-5 text-sm">
              <h3 className="mb-2 font-semibold">Przyznana ocena</h3>
              {review.summary ? (
                <p>
                  Średnia <strong>{review.summary.average.toFixed(2)} pkt</strong> · poziom <strong>{review.summary.level}</strong>
                  {review.summary.result && (
                    <>
                      {" "}
                      <Badge tone={review.summary.result === "pozytywna" ? "green" : "red"}>ocena {review.summary.result}</Badge>
                    </>
                  )}
                </p>
              ) : (
                <p className="text-muted">Ocena nie została jeszcze wystawiona.</p>
              )}
              <ul className="mt-3 space-y-1 text-slate-700">
                {review.criteria.map((c) => (
                  <li key={c.criterion_id} className="flex items-center justify-between gap-2">
                    <span>{c.name}</span>
                    <span className="whitespace-nowrap text-muted">{c.score ?? "—"} pkt</span>
                  </li>
                ))}
              </ul>
            </Card>
          </aside>
        </div>
      ) : (
        <Card className="p-6 text-sm">
          {review.deadlines.objection_deadline && !review.deadlines.objection_open ? (
            <p>Termin 7 dni na wniesienie sprzeciwu (do {fmtDate(review.deadlines.objection_deadline)}) minął. Ocena jest prawomocna.</p>
          ) : (
            <p>Sprzeciw można wnieść na etapie zapoznania się z oceną okresową.</p>
          )}
        </Card>
      )}
    </>
  );
}
