"use client";

// Metoda STAR w samoocenie: Sytuacja, Zadanie, Działanie, Rezultat. Odpowiednik FUKO po stronie pracownika -
// samoocena oparta na faktach, a nie „uważam, że jestem komunikatywny”. Lista kontrolna podpowiada, czego brakuje.

import { Check, ListChecks } from "lucide-react";
import { cn } from "@/lib/utils";
import { Textarea } from "./ui";

const STAR = [
  {
    key: "S", label: "Sytuacja", hint: "kiedy i w jakiej sprawie (kontekst)",
    re: /\b(kiedy|gdy|podczas|w czasie|w trakcie|w (styczniu|lutym|marcu|kwietniu|maju|czerwcu|lipcu|sierpniu|wrześniu|październiku|listopadzie|grudniu)|20\d\d|\d{1,2}\.\d{1,2})/i,
  },
  {
    key: "T", short: "Z", label: "Zadanie", hint: "co było Twoim zadaniem lub celem",
    re: /(zadani|miał(em|am) |należało|odpowiada(łem|łam)|celem był|trzeba było|powierzono)/i,
  },
  {
    key: "A", short: "D", label: "Działanie", hint: "co konkretnie zrobiłeś(-aś) - czasowniki w 1. osobie",
    re: /\b\w+(łem|łam)\b/i,
  },
  {
    key: "R", label: "Rezultat", hint: "co się zmieniło - najlepiej liczbą, terminem albo opinią odbiorców",
    re: /(dzięki|w efekcie|w rezultacie|skutk|efekt|zmniejsz|zwiększ|skróci|oszczędz|\d+\s?%|\b\d+\b)/i,
  },
] as const;

const TEMPLATE = STAR.map((s) => `${s.label}: `).join("\n");

/** Czy element STAR jest w tekście: wypełniona etykieta („Rezultat: …”) albo rozpoznane sformułowania. */
function present(text: string, label: string, re: RegExp) {
  const line = text.split("\n").find((l) => l.toLowerCase().startsWith(`${label.toLowerCase()}:`));
  if (line !== undefined) return line.slice(label.length + 1).trim().length >= 5;
  return re.test(text);
}

export function StarField({ value, onChange, readOnly, label }: { value: string; onChange: (v: string) => void; readOnly?: boolean; label: string }) {
  const status = STAR.map((s) => ({ ...s, ok: present(value, s.label, s.re) }));
  const missing = status.filter((s) => !s.ok);
  const empty = !value.trim();
  return (
    <div className="mt-3 space-y-1.5">
      <Textarea
        rows={value.includes("Sytuacja:") ? 5 : 3}
        readOnly={readOnly}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Przykład z okresu oceny wg STAR: sytuacja, Twoje zadanie, co zrobiłeś(-aś), jaki był rezultat…"
        aria-label={label}
      />
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-muted">STAR:</span>
        {status.map((s) => (
          <span
            key={s.key}
            title={`${s.label} - ${s.hint}`}
            className={cn(
              "inline-flex items-center gap-0.5 rounded-full border px-1.5 py-0.5",
              s.ok ? "border-emerald-300 bg-emerald-50 text-emerald-800" : "border-border bg-white text-slate-500",
            )}
          >
            {s.ok && <Check className="h-3 w-3" aria-hidden />}
            {s.label}
          </span>
        ))}
        {!readOnly && empty && (
          <button type="button" onClick={() => onChange(TEMPLATE)} className="ml-1 text-primary underline-offset-2 hover:underline">
            wstaw szablon STAR
          </button>
        )}
      </div>
      {!readOnly && !empty && missing.length > 0 && (
        <p className="text-xs text-amber-800">
          Dopisz: {missing.map((m) => `${m.label.toLowerCase()} (${m.hint})`).join("; ")}.
        </p>
      )}
    </div>
  );
}

export function StarIntro() {
  return (
    <div className="flex items-start gap-2 rounded-md border border-border bg-white/70 px-4 py-3 text-sm">
      <ListChecks className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
      <p>
        <strong>Przykłady metodą STAR.</strong> Przy każdym kryterium opisz jedną sytuację: <strong>S</strong>ytuacja (kontekst),{" "}
        <strong>Z</strong>adanie (Twój cel), <strong>D</strong>ziałanie (co zrobiłeś/-aś), <strong>R</strong>ezultat (co się zmieniło). Konkretny przykład
        przekonuje bardziej niż „uważam, że jestem komunikatywny” - lista pod polem podpowie, czego brakuje.
      </p>
    </div>
  );
}
