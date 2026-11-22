"use client";

// Okno Johari przed rozmową oceniającą: jak oceny przełożonego mają się do samooceny pracownika.
// Kolumny: co widzi pracownik / czego nie widzi; wiersze: co widzi przełożony / czego nie widzi. Liczone w kodzie.

import { useQuery } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { ErrorBox, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type JohariItem = {
  criterion_id: number;
  name: string;
  manager_score: number | null;
  self_score: number | null;
  gap: number | null;
  wheel_now: number | null;
  wheel_target: number | null;
  focus: boolean;
};
type Quadrant = { key: "arena" | "blind" | "facade" | "unknown"; title: string; subtitle: string; tip: string; items: JohariItem[] };
type Johari = { quadrants: Quadrant[]; start_with: string[]; wheel_shared: boolean };

const TONE: Record<Quadrant["key"], string> = {
  arena: "border-emerald-300 bg-emerald-50/70",
  blind: "border-sky-300 bg-sky-50/70",
  facade: "border-amber-300 bg-amber-50/70",
  unknown: "border-slate-300 bg-slate-50",
};

function Cell({ q }: { q: Quadrant }) {
  return (
    <div className={cn("flex min-h-32 flex-col rounded-md border p-2.5", TONE[q.key])}>
      <div className="font-serif text-[15px] font-semibold leading-tight">{q.title}</div>
      <div className="mb-1.5 text-[11px] text-muted">{q.subtitle}</div>
      {q.items.length === 0 ? (
        <p className="text-xs text-muted">—</p>
      ) : (
        <ul className="space-y-1 text-xs">
          {q.items.map((i) => (
            <li key={i.criterion_id} className="leading-snug">
              <span className="font-medium">{i.name}</span>
              {i.focus && <Star className="ml-1 inline h-3 w-3 fill-current text-accent" aria-label="pracownik chce nad tym pracować" />}
              <span className="block text-muted">
                Ty {i.manager_score ?? "—"} · pracownik {i.self_score ?? "—"}
                {i.wheel_now != null && ` · koło ${i.wheel_now}→${i.wheel_target}`}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-auto pt-2 text-[11px] italic text-slate-600">{q.tip}</p>
    </div>
  );
}

export function JohariWindow({ reviewId }: { reviewId: number }) {
  const { data, error, isPending } = useQuery({ queryKey: ["johari", reviewId], queryFn: () => api<Johari>(`/reviews/${reviewId}/johari`) });
  if (isPending) return <Spinner label="Układam okno Johari…" />;
  if (error) return <ErrorBox error={error} />;
  const q = Object.fromEntries(data.quadrants.map((x) => [x.key, x])) as Record<Quadrant["key"], Quadrant>;
  return (
    <div className="space-y-2">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-primary">Okno Johari</h4>
        <p className="text-xs text-muted">Twoje oceny cząstkowe a samoocena pracownika{data.wheel_shared ? " i jego koło rozwoju (★ - chce nad tym pracować)" : ""}.</p>
      </div>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-1.5 text-[10px] uppercase tracking-wide text-muted">
        <span />
        <span className="text-center">pracownik widzi</span>
        <span className="text-center">pracownik nie widzi</span>
        <span className="self-center [writing-mode:vertical-rl] rotate-180 text-center">przełożony widzi</span>
        <Cell q={q.arena} />
        <Cell q={q.blind} />
        <span className="self-center [writing-mode:vertical-rl] rotate-180 text-center">przełożony nie widzi</span>
        <Cell q={q.facade} />
        <Cell q={q.unknown} />
      </div>
      {data.start_with.length > 0 && (
        <p className="rounded-md bg-white/70 px-2.5 py-1.5 text-xs">
          <strong>Od czego zacząć rozmowę:</strong> {data.start_with.join(", ")} - największe rozbieżności.
        </p>
      )}
    </div>
  );
}
