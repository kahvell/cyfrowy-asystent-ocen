// Model 70-20-10 w IPR: ~70% rozwoju w pracy (zadania, projekty), ~20% od innych ludzi (mentoring, informacja
// zwrotna), ~10% na szkoleniach. Liczone z treści działań na bieżąco - także po edycji przez przełożonego.

import { cn } from "@/lib/utils";

export type MixKind = "praca" | "ludzie" | "szkolenie";

const PREFIX: [RegExp, MixKind][] = [
  [/^\s*praca\s*:/i, "praca"],
  [/^\s*ludzie\s*:/i, "ludzie"],
  [/^\s*(szkolenie|szkolenia|samodoskonalenie)\s*:/i, "szkolenie"],
];
const KEYWORDS: [RegExp, MixKind][] = [
  [/szkoleni|kurs|warsztat|e-learning|webinar|konferencj|studia|literatur|samodoskonal/i, "szkolenie"],
  [/mentor|coach|instrukta|shadow|informacj\w* zwrotn|wizyt\w* studyjn|superwizj|konsultacj|wymian\w* doświadcz|od innych|pod okiem|spotkani\w* z|z przełożon|z zespołem/i, "ludzie"],
];

/** Dzieli opis działań na części (średnik / nowa linia) i przypisuje każdą do 70 / 20 / 10. */
export function classifyActions(actions: string): MixKind[] {
  return actions
    // średniki, nowe linie albo lista numerowana („1. … 2. …”) i punktory
    .split(/[;\n]+|\s(?=\d+[.)]\s)|\s(?=[-•]\s)/)
    .map((p) => p.replace(/^\s*(\d+[.)]|[-•])\s*/, "").trim())
    .filter((p) => p.length > 3)
    .map((p) => PREFIX.find(([re]) => re.test(p))?.[1] ?? KEYWORDS.find(([re]) => re.test(p))?.[1] ?? "praca");
}

const META: Record<MixKind, { label: string; target: number; bar: string; dot: string }> = {
  praca: { label: "Praca (zadania, projekty)", target: 70, bar: "bg-primary", dot: "bg-primary" },
  ludzie: { label: "Ludzie (mentoring, informacja zwrotna)", target: 20, bar: "bg-sky-500", dot: "bg-sky-500" },
  szkolenie: { label: "Szkolenia i samodoskonalenie", target: 10, bar: "bg-accent", dot: "bg-accent" },
};

export function LearningMix({ actions }: { actions: string[] }) {
  const all = actions.flatMap(classifyActions);
  const total = all.length || 1;
  const share = (k: MixKind) => Math.round((all.filter((x) => x === k).length / total) * 100);
  const s = { praca: share("praca"), ludzie: share("ludzie"), szkolenie: share("szkolenie") };
  const verdict =
    all.length === 0
      ? "Dodaj działania rozwojowe do celów."
      : s.szkolenie >= 50
        ? "Program opiera się głównie na szkoleniach - dodaj zadania w pracy i uczenie się od innych."
        : s.praca < 40
          ? "Za mało rozwoju w działaniu - dodaj konkretne zadanie lub projekt."
          : s.ludzie === 0
            ? "Brakuje uczenia się od innych - dodaj mentoring albo regularną informację zwrotną."
            : "Dobre proporcje - rozwój głównie w pracy, ze wsparciem innych i szkoleniem.";
  const ok = verdict.startsWith("Dobre");
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Proporcje rozwoju - model 70-20-10</h2>
        <span className="text-xs text-muted">cel: 70 / 20 / 10</span>
      </div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`Praca ${s.praca}%, ludzie ${s.ludzie}%, szkolenia ${s.szkolenie}%`}>
        {(Object.keys(META) as MixKind[]).map((k) => (
          <div key={k} className={META[k].bar} style={{ width: `${s[k]}%` }} />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {(Object.keys(META) as MixKind[]).map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span className={cn("h-2.5 w-2.5 rounded-full", META[k].dot)} aria-hidden />
            {META[k].label}: <strong>{s[k]}%</strong> <span className="text-muted">(cel {META[k].target}%)</span>
          </li>
        ))}
      </ul>
      <p className={cn("mt-2 text-xs", ok ? "text-emerald-800" : "text-amber-800")}>{verdict}</p>
    </div>
  );
}

/** Znaczniki 70 / 20 / 10 przy jednym celu. */
export function MixTags({ actions }: { actions: string }) {
  const kinds = Array.from(new Set(classifyActions(actions)));
  if (!kinds.length) return null;
  return (
    <span className="inline-flex gap-1">
      {kinds.map((k) => (
        <span key={k} className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-medium text-white", META[k].bar)}>
          {k === "praca" ? "70 · praca" : k === "ludzie" ? "20 · ludzie" : "10 · szkolenie"}
        </span>
      ))}
    </span>
  );
}
