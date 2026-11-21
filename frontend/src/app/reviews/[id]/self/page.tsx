"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Button, Card, ErrorBox, PageTitle, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import type { SelfAssessment } from "@/lib/types";
import { cn, fmtDate, SCALE } from "@/lib/utils";

type Items = Record<string, { score: number | null; comment: string }>;

export default function SelfAssessmentPage() {
  const { id } = useParams<{ id: string }>();
  const reviewId = Number(id);
  const { data, error, isPending } = useQuery({
    queryKey: ["self", reviewId],
    queryFn: () => api<SelfAssessment>(`/reviews/${reviewId}/self-assessment`),
  });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  return <SelfForm key={data.submitted_at ?? "draft"} data={data} reviewId={reviewId} />;
}

function SelfForm({ data, reviewId }: { data: SelfAssessment; reviewId: number }) {
  const qc = useQueryClient();
  const [items, setItems] = useState<Items>(data.items);
  const [summary, setSummary] = useState(data.summary);

  const save = useMutation({
    mutationFn: (submit: boolean) =>
      api<SelfAssessment>(`/reviews/${reviewId}/self-assessment`, {
        method: "PUT",
        json: { items: Object.fromEntries(Object.entries(items).map(([k, v]) => [Number(k), v])), summary, submit },
      }),
    onSuccess: (r) => qc.setQueryData(["self", reviewId], r),
  });

  const locked = !!data.submitted_at || !data.open;
  const set = (cid: number, patch: Partial<{ score: number | null; comment: string }>) =>
    setItems((prev) => ({ ...prev, [cid]: { score: prev[cid]?.score ?? null, comment: prev[cid]?.comment ?? "", ...patch } }));

  return (
    <>
      <PageTitle
        title="Samoocena"
        subtitle={
          data.submitted_at
            ? `Przekazana przełożonemu ${fmtDate(data.submitted_at)}. Będzie punktem wyjścia do rozmowy oceniającej.`
            : !data.open
              ? "Samoocenę można było przekazać do czasu przekazania oceny do rozmowy oceniającej. Swoją perspektywę przedstawisz w rozmowie."
              : "Twoja perspektywa przed rozmową oceniającą - przekaż ją, zanim przełożony przekaże ocenę do rozmowy. Podaj przykłady: to one najlepiej pokazują Twoją pracę."
        }
      />
      <div className="space-y-4">
        {data.criteria.map((c) => {
          const it = items[c.criterion_id] ?? { score: null, comment: "" };
          return (
            <Card key={c.criterion_id} className="p-5">
              <h3 className="font-semibold">{c.name}</h3>
              <p className="mt-1 text-xs text-muted">{c.description}</p>
              <div className="mt-3 grid grid-cols-5 gap-1.5">
                {SCALE.map((s) => (
                  <button
                    key={s.value}
                    disabled={locked}
                    aria-pressed={it.score === s.value}
                    onClick={() => set(c.criterion_id, { score: s.value })}
                    className={cn(
                      "rounded-md border px-1 py-1.5 text-xs",
                      it.score === s.value ? "border-primary bg-primary text-white" : "border-border bg-white hover:bg-slate-50",
                    )}
                  >
                    <div className="text-base font-semibold">{s.value}</div>
                    <div className="hidden sm:block">{s.short}</div>
                  </button>
                ))}
              </div>
              <Textarea
                className="mt-3"
                rows={2}
                readOnly={locked}
                value={it.comment}
                onChange={(e) => set(c.criterion_id, { comment: e.target.value })}
                placeholder="Przykład z okresu oceny…"
                aria-label={`Komentarz: ${c.name}`}
              />
            </Card>
          );
        })}
        <Card className="p-5">
          <label htmlFor="summary" className="mb-1 block font-semibold">
            Kierunki rozwoju, które Cię interesują
          </label>
          <Textarea id="summary" rows={3} readOnly={locked} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </Card>
        <ErrorBox error={save.error} />
        {!locked && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => save.mutate(false)} loading={save.isPending}>
              Zapisz roboczo
            </Button>
            <Button onClick={() => confirm("Po przekazaniu nie będzie można zmienić samooceny. Przekazać?") && save.mutate(true)} loading={save.isPending}>
              <Send className="h-4 w-4" aria-hidden /> Przekaż przełożonemu
            </Button>
          </div>
        )}
      </div>
    </>
  );
}
