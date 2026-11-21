"use client";

import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Label, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { TeamMember, TeamStats } from "@/lib/types";
import { fmtDate, scaleLabel, STATUS_LABEL, statusTone } from "@/lib/utils";

// Skala porządkowa z punktem środkowym -> paleta rozbieżna czerwień <-> niebieski, szary środek.
const LEVELS = [
  { key: "znacznie poniżej oczekiwań", short: "zn. poniżej", color: "#c23a3a" },
  { key: "poniżej oczekiwań", short: "poniżej", color: "#ef9a99" },
  { key: "na poziomie oczekiwań", short: "na poziomie", color: "#cfcec8" },
  { key: "powyżej oczekiwań", short: "powyżej", color: "#86b6ef" },
  { key: "znacznie powyżej oczekiwań", short: "zn. powyżej", color: "#1c5cab" },
];
const MUTED = "#5d6a7e";
const GRID = "#e6e9ee";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-border p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

function LevelsChart({ levels, total }: { levels: Record<string, number>; total: number }) {
  const rows = LEVELS.map((l) => ({
    name: l.short,
    key: l.key,
    value: levels[l.key] ?? 0,
    pct: total ? Math.round(((levels[l.key] ?? 0) / total) * 100) : 0,
    color: l.color,
  }));
  return (
    <div className="h-64 p-5">
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ left: 8, right: 16 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="name" tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip
            cursor={{ fill: "rgba(31,63,120,0.06)" }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <div className="rounded-md border border-border bg-white px-3 py-2 text-xs shadow-md">
                  <div className="mb-1 font-medium">{payload[0].payload.key}</div>
                  <div className="flex justify-between gap-4">
                    <span className="text-muted">liczba ocen</span>
                    <span className="font-medium tabular-nums">{payload[0].payload.value} ({payload[0].payload.pct}%)</span>
                  </div>
                </div>
              ) : null
            }
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
            {rows.map((r) => (
              <Cell key={r.key} fill={r.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function TeamStatsPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const { data: members, error: membersError, isPending: membersPending } = useQuery({
    queryKey: ["team-stats-members"],
    queryFn: () => api<TeamMember[]>("/employees"),
  });

  const params = new URLSearchParams();
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  [...selected].forEach((id) => params.append("employee_ids", String(id)));
  const { data: stats, error, isPending } = useQuery({
    queryKey: ["team-stats", from, to, [...selected].sort().join(",")],
    queryFn: () => api<TeamStats>(`/analytics/team${params.toString() ? `?${params}` : ""}`),
  });

  if (membersPending || isPending) return <Spinner />;
  if (membersError || error) return <ErrorBox error={membersError ?? error} />;

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allSelected = !!members?.length && selected.size === members.length;
  const summary = stats.summary;
  const positive = summary.results.pozytywna ?? 0;
  const negative = summary.results.negatywna ?? 0;

  return (
    <>
      <PageTitle
        title="Statystyki zespołu"
        subtitle={`Wyniki ocen okresowych Twoich podwładnych · ${summary.n_reviews} sporządzonych ocen dla ${summary.n_employees} osób`}
        action={<Badge tone="blue">pełne dane zespołu · bez progu k-anonimowości</Badge>}
      />

      <Card className="mb-6">
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="sf">Okres oceny od</Label>
              <Input id="sf" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="st">do</Label>
              <Input id="st" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
            {(from || to) && (
              <Button variant="ghost" onClick={() => { setFrom(""); setTo(""); }}>
                Wyczyść zakres
              </Button>
            )}
          </div>
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <Label>Podwładni</Label>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-xs text-muted">
                  {selected.size === 0 ? "wybrano: wszyscy" : `wybrano: ${selected.size} z ${members?.length ?? 0}`}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setSelected(allSelected ? new Set() : new Set((members ?? []).map((m) => m.id)))}
                >
                  {allSelected ? "Wyczyść wybór" : "Zaznacz wszystkich"}
                </Button>
              </div>
            </div>
            <div className="grid max-h-56 gap-1 overflow-y-auto rounded-md border border-border p-3 sm:grid-cols-2 lg:grid-cols-3">
              {(members ?? []).map((m) => (
                <label key={m.id} className="flex items-center gap-2 rounded px-1 py-1 text-sm hover:bg-slate-50">
                  <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />
                  <span className="font-medium">{m.full_name}</span>
                  <span className="truncate text-xs text-muted">{m.position}</span>
                </label>
              ))}
              {!members?.length && <p className="text-sm text-muted">Brak podwładnych w systemie.</p>}
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Podsumowanie zespołu" subtitle="Zakres wybrany filtrem daty i listą osób." />
          <div className="grid gap-3 p-5 sm:grid-cols-2">
            <Stat label="Pracowników" value={String(summary.n_employees)} />
            <Stat label="Sporządzonych ocen" value={String(summary.n_reviews)} />
            <Stat label="Średnia ocen" value={summary.average != null ? `${summary.average} pkt` : "-"} />
            <Stat label="Oceny pozytywne / negatywne" value={`${positive} / ${negative}`} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Rozkład poziomów ocen" subtitle="Poziomy ogólne ocen sporządzonych w wybranym zakresie." />
          {summary.n_reviews ? (
            <LevelsChart levels={summary.levels} total={summary.n_reviews} />
          ) : (
            <p className="p-5 text-sm text-muted">Brak sporządzonych ocen w wybranym zakresie.</p>
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Wyniki ocen podwładnych" subtitle="Ostatnia ocena każdej osoby; rozwiń, aby zobaczyć wszystkie cykle." />
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-5 py-3 font-medium">Pracownik</th>
              <th className="px-5 py-3 font-medium">Ostatnia ocena</th>
              <th className="px-5 py-3 font-medium">Średnia</th>
              <th className="px-5 py-3 font-medium">Liczba ocen</th>
            </tr>
          </thead>
          <tbody>
            {(stats.employees ?? []).map((e) => (
              <tr key={e.employee_id} className="border-b border-border align-top last:border-0">
                <td className="px-5 py-3">
                  <div className="font-medium">{e.full_name}</div>
                  <div className="text-xs text-muted">{e.position}{e.department ? ` · ${e.department}` : ""}</div>
                </td>
                <td className="px-5 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={e.latest_result === "negatywna" ? "red" : "green"}>
                      {e.latest_level ?? scaleLabel(e.latest_score)}
                    </Badge>
                    <Badge tone={statusTone(e.reviews[0].status)}>{STATUS_LABEL[e.reviews[0].status]}</Badge>
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    okres {fmtDate(e.reviews[0].period_start)} – {fmtDate(e.reviews[0].period_end)} · sporządzona {fmtDate(e.reviews[0].drawn_up)}
                  </div>
                </td>
                <td className="px-5 py-3 tabular-nums">{e.average != null ? `${e.average} pkt` : "-"}</td>
                <td className="px-5 py-3 tabular-nums">{e.n}</td>
              </tr>
            ))}
            {!stats.employees?.length && (
              <tr>
                <td colSpan={4} className="px-5 py-6 text-center text-sm text-muted">
                  Brak sporządzonych ocen w wybranym zakresie.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}
