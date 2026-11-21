"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, EyeOff, Lock, PenLine } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Reminders } from "@/components/reminders";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Label, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Cycle, Overview } from "@/lib/types";
import { fmtDate } from "@/lib/utils";

// Skala porządkowa z punktem środkowym („na poziomie oczekiwań”) -> paleta rozbieżna czerwień <-> niebieski, szary środek.
const LEVELS = [
  { key: "znacznie poniżej oczekiwań", short: "zn. poniżej", color: "#c23a3a" },
  { key: "poniżej oczekiwań", short: "poniżej", color: "#ef9a99" },
  { key: "na poziomie oczekiwań", short: "na poziomie", color: "#cfcec8" },
  { key: "powyżej oczekiwań", short: "powyżej", color: "#86b6ef" },
  { key: "znacznie powyżej oczekiwań", short: "zn. powyżej", color: "#1c5cab" },
];
const INK = "#1b2433";
const MUTED = "#5d6a7e";
const GRID = "#e6e9ee";

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-700" aria-label="Legenda">
      {LEVELS.map((l) => (
        <li key={l.key} className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm" style={{ background: l.color }} aria-hidden /> {l.key}
        </li>
      ))}
    </ul>
  );
}

function TooltipBox({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="rounded-md border border-border bg-white px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-medium">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4">
          <span className="text-muted">{k}</span>
          <span className="font-medium tabular-nums">{v}</span>
        </div>
      ))}
    </div>
  );
}

function Distribution({ data }: { data: Overview["distribution"] }) {
  const visible = data.departments.filter((d) => !d.hidden);
  const rows = visible.map((d) => {
    const row: Record<string, number | string> = { department: d.department, n: d.n };
    LEVELS.forEach((l) => (row[l.key] = Math.round(((d.levels[l.key] ?? 0) / d.n) * 100)));
    return row;
  });
  const hidden = data.departments.filter((d) => d.hidden);
  return (
    <Card>
      <CardHeader title="Rozkład ocen w komórkach" subtitle="Udział poziomów ogólnych (%). Wykrywa „inflację ocen” - gdy prawie wszyscy dostają najwyższe noty." />
      <div className="space-y-3 p-5">
        <Legend />
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }} barCategoryGap={10}>
              <CartesianGrid horizontal={false} stroke={GRID} />
              <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="department" width={170} tick={{ fill: INK, fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip
                cursor={{ fill: "rgba(31,63,120,0.06)" }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <TooltipBox title={`${label} (n=${payload[0].payload.n})`} rows={LEVELS.map((l) => [l.key, `${payload[0].payload[l.key]}%`])} />
                  ) : null
                }
              />
              {LEVELS.map((l, i) => (
                <Bar
                  key={l.key}
                  dataKey={l.key}
                  stackId="a"
                  fill={l.color}
                  stroke="#ffffff"
                  strokeWidth={2}
                  radius={i === LEVELS.length - 1 ? [0, 4, 4, 0] : i === 0 ? [4, 0, 0, 4] : 0}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex flex-wrap gap-2">
          {visible
            .filter((d) => d.flag)
            .map((d) => (
              <Badge key={d.department} tone="amber">
                <AlertTriangle className="h-3 w-3" aria-hidden /> {d.department}: {d.flag} ({Math.round((d.top_share ?? 0) * 100)}% ocen powyżej oczekiwań)
              </Badge>
            ))}
          {hidden.map((d) => (
            <Badge key={d.department}>
              <EyeOff className="h-3 w-3" aria-hidden /> {d.department}: ukryte (n &lt; {data.k})
            </Badge>
          ))}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer text-primary">Pokaż tabelę</summary>
          <table className="mt-2 w-full text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1">Komórka</th>
                <th>n</th>
                {LEVELS.map((l) => (
                  <th key={l.key}>{l.short}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.departments.map((d) => (
                <tr key={d.department} className="border-t border-border">
                  <td className="py-1">{d.department}</td>
                  <td>{d.n}</td>
                  {LEVELS.map((l) => (
                    <td key={l.key}>{d.levels[l.key] ?? "-"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </div>
    </Card>
  );
}

function Gaps({ data }: { data: Overview["competency_gaps"] }) {
  const rows = data.criteria.filter((c) => !c.hidden);
  return (
    <Card>
      <CardHeader title="Luki kompetencyjne urzędu" subtitle="Średnia ocena cząstkowa w kryterium (1–9 pkt). Linia: „na poziomie oczekiwań” (5 pkt)." />
      <div className="h-64 p-5">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 32 }} barCategoryGap={8}>
            <CartesianGrid horizontal={false} stroke={GRID} />
            <XAxis type="number" domain={[0, 9]} ticks={[1, 3, 5, 7, 9]} tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" width={210} tick={{ fill: INK, fontSize: 12 }} axisLine={false} tickLine={false} />
            <ReferenceLine x={5} stroke={MUTED} strokeDasharray="4 3" />
            <Tooltip
              cursor={{ fill: "rgba(31,63,120,0.06)" }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <TooltipBox title={payload[0].payload.name} rows={[["średnia", `${payload[0].payload.average} pkt`], ["liczba ocen", String(payload[0].payload.n)]]} />
                ) : null
              }
            />
            <Bar dataKey="average" fill="#2a78d6" radius={[0, 4, 4, 0]} label={{ position: "right", fill: INK, fontSize: 11 }} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function Calibration({ data }: { data: Overview["reviewer_calibration"] }) {
  const rows = data.filter((r) => !r.hidden);
  return (
    <Card>
      <CardHeader
        title="Kalibracja oceniających"
        subtitle={`Różnica średniej oceniającego od średniej urzędu (${rows[0]?.office_average ?? "-"} pkt). Powyżej +1 pkt: „łagodny”, poniżej −1: „surowy”.`}
      />
      <div className="h-56 p-5">
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 40 }} barCategoryGap={10}>
            <CartesianGrid horizontal={false} stroke={GRID} />
            <XAxis type="number" domain={[-3, 3]} tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="reviewer_name" width={150} tick={{ fill: INK, fontSize: 12 }} axisLine={false} tickLine={false} />
            <ReferenceLine x={0} stroke={MUTED} />
            <Tooltip
              cursor={{ fill: "rgba(31,63,120,0.06)" }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <TooltipBox
                    title={payload[0].payload.reviewer_name}
                    rows={[
                      ["średnia oceniającego", `${payload[0].payload.average} pkt`],
                      ["różnica", `${payload[0].payload.delta > 0 ? "+" : ""}${payload[0].payload.delta} pkt`],
                      ["liczba ocen", String(payload[0].payload.n)],
                    ]}
                  />
                ) : null
              }
            />
            <Bar dataKey="delta" radius={4} label={{ position: "right", fill: INK, fontSize: 11, formatter: (v: unknown) => `${Number(v) > 0 ? "+" : ""}${v}` }}>
              {rows.map((r) => (
                <Cell key={r.reviewer_id} fill={r.delta >= 0 ? "#2a78d6" : "#e34948"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap gap-2 px-5 pb-5">
        {rows
          .filter((r) => r.flag)
          .map((r) => (
            <Badge key={r.reviewer_id} tone="amber">
              <AlertTriangle className="h-3 w-3" aria-hidden /> {r.reviewer_name}: oceniający {r.flag}
            </Badge>
          ))}
      </div>
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-border p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const qs = new URLSearchParams();
  if (from) qs.set("date_from", from);
  if (to) qs.set("date_to", to);
  const suffix = qs.toString() ? `?${qs}` : "";
  const { data, error, isPending } = useQuery({
    queryKey: ["overview", from, to],
    queryFn: () => api<Overview>(`/analytics/overview${suffix}`),
  });
  const { data: cycles } = useQuery({ queryKey: ["cycles"], queryFn: () => api<Cycle[]>("/cycles") });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const cycle = cycles?.find((c) => c.id === data.cycle_id);
  const scopeLabel = from || to
    ? `okres oceny ${from ? fmtDate(from) : "…"} – ${to ? fmtDate(to) : "…"}`
    : cycle?.name ?? "Cykl";
  const adoption = data.ai_adoption.by_kind.draft_justification ?? { accepted: 0, edited: 0, rejected: 0, pending: 0 };
  const decided = adoption.accepted + adoption.edited + adoption.rejected;
  const pct = (n: number) => (decided ? `${Math.round((n / decided) * 100)}%` : "-");
  const g = data.gender_gap;

  return (
    <>
      <PageTitle
        title="Dashboard urzędu"
        subtitle={`${scopeLabel} · ${data.distribution.total.n} zatwierdzonych ocen`}
        action={
          <Badge tone="slate">
            <Lock className="h-3 w-3" aria-hidden /> wyłącznie dane zagregowane · k-anonimowość: grupy &lt; {data.distribution.k} osób ukryte
          </Badge>
        }
      />
      <Card className="mb-6">
        <div className="flex flex-wrap items-end gap-3 p-5">
          <div>
            <Label htmlFor="df">Okres oceny od</Label>
            <Input id="df" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="dt">do</Label>
            <Input id="dt" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
          {(from || to) && (
            <Button variant="ghost" onClick={() => { setFrom(""); setTo(""); }}>
              Wyczyść zakres
            </Button>
          )}
          <p className="text-xs text-muted">
            Statystyki obejmują oceny, których okres oceny mieści się w wybranym zakresie. Bez filtra - domyślny najnowszy zamknięty cykl.
          </p>
        </div>
      </Card>
      <Reminders title="Sprawy kadrowe: sprzeciwy, stopnie służbowe, ponowne oceny" />
      <div className="grid gap-6 xl:grid-cols-2">
        <Distribution data={data.distribution} />
        <Calibration data={data.reviewer_calibration} />
        <Gaps data={data.competency_gaps} />
        <Card>
          <CardHeader title="Równe traktowanie i adopcja AI" />
          <div className="grid gap-3 p-5 sm:grid-cols-2">
            <Stat label="Średnia: kobiety" value={g.groups.K?.average != null ? `${g.groups.K.average} pkt` : "ukryte"} hint={`n = ${g.groups.K?.n ?? 0}`} />
            <Stat label="Średnia: mężczyźni" value={g.groups.M?.average != null ? `${g.groups.M.average} pkt` : "ukryte"} hint={`n = ${g.groups.M?.n ?? 0}`} />
            <Stat
              label="Różnica K − M"
              value={g.gap_k_minus_m != null ? `${g.gap_k_minus_m > 0 ? "+" : ""}${g.gap_k_minus_m} pkt` : "-"}
              hint={g.gap_k_minus_m != null && Math.abs(g.gap_k_minus_m) >= 1 ? "do wyjaśnienia" : "bez istotnej różnicy"}
            />
            <Stat label="Propozycje AI: zaakceptowane" value={pct(adoption.accepted)} hint={`z ${decided} decyzji`} />
            <Stat label="Propozycje AI: edytowane przez człowieka" value={pct(adoption.edited)} />
            <Stat label="Propozycje AI: odrzucone" value={pct(adoption.rejected)} />
          </div>
          <p className="flex items-start gap-1.5 px-5 pb-5 text-xs text-muted">
            <PenLine className="mt-0.5 h-3 w-3 shrink-0 text-ai" aria-hidden />
            Wysoki odsetek edycji i odrzuceń to dobry sygnał: przełożeni weryfikują propozycje AI, a nie przepisują ich bezrefleksyjnie.
          </p>
        </Card>
      </div>
    </>
  );
}
