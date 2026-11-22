"use client";

// Koło rozwoju (etap I, § 5): oceniany zaznacza, gdzie jest i gdzie chce być w każdym kryterium (ta sama skala
// 1/3/5/7/9 co oceny przełożonego, żeby skale się nie mieszały), wskazuje maks. 2 obszary do pracy i może zaproponować
// kryterium dodatkowe. Przełożony widzi koło po udostępnieniu - jako punkt wyjścia do rozmowy rozpoczynającej.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Send, Target } from "lucide-react";
import { useState } from "react";
import { Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { Badge, Button, Card, CardHeader, ErrorBox, Label, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, fmtDate, SCALE } from "@/lib/utils";

type WheelItem = { now: number; target: number };
type Wheel = {
  review_id: number;
  criteria: { criterion_id: number; name: string; is_additional: boolean; indicators: string[] }[];
  proposable: { criterion_id: number; name: string }[];
  items: Record<string, WheelItem>;
  focus: number[];
  proposed_criterion_id: number | null;
  note: string;
  shared_at: string | null;
  editable: boolean;
};

const MAX_FOCUS = 2;
const DEFAULT: WheelItem = { now: 5, target: 7 };

function WheelChart({ wheel, items }: { wheel: Wheel; items: Record<string, WheelItem> }) {
  const data = wheel.criteria.map((c) => ({
    name: c.name.length > 22 ? `${c.name.slice(0, 20)}…` : c.name,
    Teraz: items[c.criterion_id]?.now ?? 0,
    Cel: items[c.criterion_id]?.target ?? 0,
  }));
  return (
    <div className="h-72 w-full" role="img" aria-label="Koło rozwoju: poziom obecny i docelowy w każdym kryterium">
      <ResponsiveContainer>
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--muted)" }} />
          <PolarRadiusAxis domain={[0, 9]} ticks={[1, 3, 5, 7, 9]} tick={{ fontSize: 9, fill: "var(--muted)" }} axisLine={false} />
          <Radar name="Cel" dataKey="Cel" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.12} strokeDasharray="4 3" />
          <Radar name="Teraz" dataKey="Teraz" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.3} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Tooltip />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ta sama skala co oceny cząstkowe przełożonego i samoocena: 1 / 3 / 5 / 7 / 9
function Scale({ value, onChange, disabled, label }: { value: number; onChange: (v: number) => void; disabled?: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 shrink-0 text-xs text-muted">{label}</span>
      <div className="grid w-full grid-cols-5 gap-1" role="radiogroup" aria-label={label}>
        {SCALE.map((s) => (
          <button
            key={s.value}
            type="button"
            role="radio"
            aria-checked={value === s.value}
            disabled={disabled}
            title={s.label}
            onClick={() => onChange(s.value)}
            className={cn(
              "rounded-md border px-1 py-1 text-xs leading-tight disabled:cursor-not-allowed",
              value === s.value ? "border-primary bg-primary text-white" : "border-border bg-white hover:bg-slate-50",
            )}
          >
            <span className="block font-semibold">{s.value}</span>
            <span className="hidden text-[10px] xl:block">{s.short}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** Oceniany: wypełnia i udostępnia koło. */
export function DevelopmentWheelEditor({ reviewId }: { reviewId: number }) {
  const { data, error, isPending } = useQuery({ queryKey: ["wheel", reviewId], queryFn: () => api<Wheel>(`/reviews/${reviewId}/wheel`) });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  return <WheelForm key={`${data.shared_at}`} wheel={data} />;
}

function WheelForm({ wheel }: { wheel: Wheel }) {
  const qc = useQueryClient();
  const [items, setItems] = useState<Record<string, WheelItem>>(() =>
    Object.fromEntries(wheel.criteria.map((c) => [c.criterion_id, wheel.items[c.criterion_id] ?? DEFAULT])),
  );
  const [focus, setFocus] = useState<number[]>(wheel.focus);
  const [proposed, setProposed] = useState<number | null>(wheel.proposed_criterion_id);
  const [note, setNote] = useState(wheel.note);
  const save = useMutation({
    mutationFn: (share: boolean) =>
      api<Wheel>(`/reviews/${wheel.review_id}/wheel`, { method: "PUT", json: { items, focus, proposed_criterion_id: proposed, note, share } }),
    onSuccess: (w) => qc.setQueryData(["wheel", wheel.review_id], w),
  });
  const ro = !wheel.editable;
  const set = (cid: number, patch: Partial<WheelItem>) => setItems((p) => ({ ...p, [cid]: { ...(p[cid] ?? DEFAULT), ...patch } }));
  const toggleFocus = (cid: number) =>
    setFocus((f) => (f.includes(cid) ? f.filter((x) => x !== cid) : f.length < MAX_FOCUS ? [...f, cid] : f));

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" aria-hidden /> Twoje koło rozwoju
          </span>
        }
        subtitle="Gdzie jesteś, gdzie chcesz być i nad czym chcesz pracować - przed rozmową rozpoczynającą"
        action={wheel.shared_at ? <Badge tone="green">udostępnione {fmtDate(wheel.shared_at)}</Badge> : undefined}
      />
      <div className="space-y-4 p-4 text-sm">
        {!wheel.shared_at && !ro && (
          <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900">
            Najlepiej udostępnij koło przed rozmową rozpoczynającą - przełożony uwzględni je przy wyborze kryteriów.
          </p>
        )}
        <p className="text-slate-600">
          Skala jak w ocenie okresowej: 1 - znacznie poniżej, 5 - na poziomie, 9 - znacznie powyżej oczekiwań. To Twoja perspektywa przed rozmową, a nie samoocena. Zaznacz maksymalnie {MAX_FOCUS} kryteria, nad którymi chcesz pracować w najbliższym okresie -
          porozmawiacie o nich w rozmowie rozpoczynającej.
        </p>
        <WheelChart wheel={wheel} items={items} />
        <ul className="space-y-3">
          {wheel.criteria.map((c) => {
            const it = items[c.criterion_id] ?? DEFAULT;
            const on = focus.includes(c.criterion_id);
            return (
              <li key={c.criterion_id} className={cn("rounded-md border p-3", on ? "border-primary bg-primary/5" : "border-border bg-white")}>
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {c.name}
                    {c.is_additional && <span className="ml-1 text-xs font-normal text-muted">(dodatkowe)</span>}
                  </span>
                  <label className={cn("flex items-center gap-1.5 text-xs", ro && "opacity-60")}>
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={ro || (!on && focus.length >= MAX_FOCUS)}
                      onChange={() => toggleFocus(c.criterion_id)}
                    />
                    chcę nad tym pracować
                  </label>
                </div>
                <Scale label="teraz" value={it.now} disabled={ro} onChange={(v) => set(c.criterion_id, { now: v })} />
                <Scale label="cel" value={it.target} disabled={ro} onChange={(v) => set(c.criterion_id, { target: v })} />
              </li>
            );
          })}
        </ul>
        <div>
          <Label htmlFor="wheel-propose">Zaproponuj kryterium dodatkowe (opcjonalnie)</Label>
          <select
            id="wheel-propose"
            disabled={ro}
            value={proposed ?? ""}
            onChange={(e) => setProposed(e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-md border border-border bg-white px-3 py-2 text-sm disabled:bg-slate-50"
          >
            <option value="">- bez propozycji -</option>
            {wheel.proposable.map((c) => (
              <option key={c.criterion_id} value={c.criterion_id}>
                {c.name}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted">Kryteria dodatkowe wybiera przełożony (§ 5 ust. 2) - Twoja propozycja jest punktem do rozmowy.</p>
        </div>
        <div>
          <Label htmlFor="wheel-note">Co chcesz powiedzieć przełożonemu o swoich celach?</Label>
          <Textarea
            id="wheel-note"
            rows={3}
            readOnly={ro}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Np. „Chcę bardziej samodzielnie prowadzić projekty i potrzebuję w tym wsparcia mentora”."
          />
        </div>
        {!ro && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => save.mutate(false)} loading={save.isPending && !save.variables}>
              Zapisz
            </Button>
            <Button onClick={() => save.mutate(true)} loading={save.isPending && !!save.variables}>
              <Send className="h-4 w-4" aria-hidden /> {wheel.shared_at ? "Zapisz zmiany (przełożony widzi koło)" : "Udostępnij przełożonemu"}
            </Button>
          </div>
        )}
        {!wheel.shared_at && (
          <p className="flex items-center gap-1.5 text-xs text-muted">
            <Lock className="h-3 w-3" aria-hidden /> Dopóki nie udostępnisz, koło widzisz tylko Ty.
          </p>
        )}
        <ErrorBox error={save.error} />
      </div>
    </Card>
  );
}

/** Oceniający: podgląd udostępnionego koła przed rozmową rozpoczynającą. */
export function DevelopmentWheelView({ reviewId }: { reviewId: number }) {
  const { data: w } = useQuery({ queryKey: ["wheel", reviewId], queryFn: () => api<Wheel>(`/reviews/${reviewId}/wheel`) });
  if (!w) return null;
  const name = (id: number | null) => w.criteria.find((c) => c.criterion_id === id)?.name ?? w.proposable.find((c) => c.criterion_id === id)?.name;
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Target className="h-4 w-4 text-primary" aria-hidden /> Koło rozwoju pracownika
          </span>
        }
        subtitle="Perspektywa pracownika przed rozmową rozpoczynającą"
        action={w.shared_at ? <Badge tone="green">udostępnione {fmtDate(w.shared_at)}</Badge> : <Badge tone="amber">nie udostępnione</Badge>}
      />
      <div className="space-y-3 p-4 text-sm">
        {!w.shared_at ? (
          <p className="text-muted">Pracownik nie udostępnił jeszcze koła rozwoju. Gdy to zrobi, dostaniesz powiadomienie, a jego wskazania uwzględni propozycja kryteriów.</p>
        ) : (
          <>
            <WheelChart wheel={w} items={w.items} />
            {w.focus.length > 0 && (
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-primary">Chce pracować nad</h4>
                <ul className="space-y-0.5">
                  {w.focus.map((id) => {
                    const it = w.items[id];
                    return (
                      <li key={id}>
                        <strong>{name(id)}</strong>
                        {it && <span className="text-muted"> - teraz {it.now}, cel {it.target}</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
            {w.proposed_criterion_id && (
              <p>
                <span className="text-xs font-semibold uppercase tracking-wide text-primary">Proponuje kryterium dodatkowe: </span>
                <strong>{name(w.proposed_criterion_id)}</strong>
              </p>
            )}
            {w.note && <p className="rounded-md bg-slate-50 p-2 italic text-slate-700">„{w.note}”</p>}
          </>
        )}
      </div>
    </Card>
  );
}
