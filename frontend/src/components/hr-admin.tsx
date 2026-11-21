"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Download, FileSpreadsheet, History, Pencil, Plus, Trash2, Upload, UserCog } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Label, Textarea } from "@/components/ui";
import { api, getToken } from "@/lib/api";
import { cn, fmtDate, SCALE, STATUS_LABEL, statusTone } from "@/lib/utils";

const select = "w-full rounded-md border border-border bg-white px-3 py-2 text-sm";

async function downloadFile(path: string, filename: string) {
  const res = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!res.ok) throw new Error("Nie udało się pobrać pliku");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ------------------------------------------------------------------ schemat urzędu

interface Dept {
  id: number;
  name: string;
  employees: number;
  head: string | null;
}

export function StructurePanel() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["hr-departments"], queryFn: () => api<Dept[]>("/admin/departments") });
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["hr-departments"] });
    qc.invalidateQueries({ queryKey: ["hr-structure"] });
    qc.invalidateQueries({ queryKey: ["hr-employees"] });
  };
  const add = useMutation({ mutationFn: () => api("/admin/departments", { method: "POST", json: { name } }), onSuccess: () => (setName(""), refresh()) });
  const rename = useMutation({
    mutationFn: (d: { id: number; name: string }) => api(`/admin/departments/${d.id}`, { method: "PATCH", json: { name: d.name } }),
    onSuccess: () => (setEditing(null), refresh()),
  });
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Building2 className="h-4 w-4 text-primary" aria-hidden /> Schemat urzędu
          </span>
        }
        subtitle="Komórki organizacyjne. Podległość służbową (kto kogo ocenia) ustawiasz w danych pracownika."
      />
      <ul className="divide-y divide-border text-sm">
        {data.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
            {editing?.id === d.id ? (
              <>
                <Input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className="max-w-sm" aria-label="Nazwa komórki" />
                <Button size="sm" onClick={() => rename.mutate(editing)} loading={rename.isPending}>
                  Zapisz
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                  Anuluj
                </Button>
              </>
            ) : (
              <>
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{d.name}</div>
                  <div className="text-xs text-muted">
                    {d.employees} osób · kierujący: {d.head ?? "brak"}
                  </div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setEditing({ id: d.id, name: d.name })} aria-label={`Zmień nazwę: ${d.name}`}>
                  <Pencil className="h-4 w-4" aria-hidden /> Zmień nazwę
                </Button>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2 border-t border-border px-5 py-4">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nazwa nowej komórki, np. Wydział Kontroli" className="max-w-sm" aria-label="Nowa komórka" />
        <Button onClick={() => add.mutate()} disabled={name.trim().length < 3} loading={add.isPending}>
          <Plus className="h-4 w-4" aria-hidden /> Dodaj komórkę
        </Button>
        <ErrorBox error={add.error || rename.error} />
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ zastępstwa

interface Sub {
  id: number;
  absent_name: string;
  deputy_name: string;
  start: string;
  end: string;
  note: string;
  active: boolean;
}

export function SubstitutionsPanel({ people }: { people: { id: number; full_name: string; position: string; active: boolean }[] }) {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["hr-subs"], queryFn: () => api<Sub[]>("/admin/substitutions") });
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState({ absent_employee_id: 0, deputy_employee_id: 0, start: today, end: today, note: "" });
  const add = useMutation({
    mutationFn: () => api("/admin/substitutions", { method: "POST", json: f }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr-subs"] }),
  });
  const del = useMutation({
    mutationFn: (id: number) => api(`/admin/substitutions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hr-subs"] }),
  });
  const active = people.filter((p) => p.active);
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <UserCog className="h-4 w-4 text-primary" aria-hidden /> Zastępstwa przełożonych
          </span>
        }
        subtitle="W okresie zastępstwa zastępca prowadzi sprawy ocen okresowych zespołu osoby nieobecnej (na wcześniej wybranych kryteriach, § 9 ust. 3)."
      />
      <div className="grid gap-3 p-5 text-sm sm:grid-cols-2">
        <div>
          <Label htmlFor="abs">Nieobecny przełożony</Label>
          <select id="abs" className={select} value={f.absent_employee_id} onChange={(e) => setF({ ...f, absent_employee_id: Number(e.target.value) })}>
            <option value={0}>- wybierz -</option>
            {active.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name} · {p.position}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="dep">Zastępca</Label>
          <select id="dep" className={select} value={f.deputy_employee_id} onChange={(e) => setF({ ...f, deputy_employee_id: Number(e.target.value) })}>
            <option value={0}>- wybierz -</option>
            {active
              .filter((p) => p.id !== f.absent_employee_id)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name} · {p.position}
                </option>
              ))}
          </select>
        </div>
        <div className="flex gap-2">
          <div>
            <Label htmlFor="ss">Od</Label>
            <Input id="ss" type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} />
          </div>
          <div>
            <Label htmlFor="se">Do</Label>
            <Input id="se" type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} />
          </div>
        </div>
        <div>
          <Label htmlFor="sn">Uwagi</Label>
          <Input id="sn" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="np. urlop wypoczynkowy" />
        </div>
        <div className="sm:col-span-2">
          <Button onClick={() => add.mutate()} disabled={!f.absent_employee_id || !f.deputy_employee_id} loading={add.isPending}>
            <Plus className="h-4 w-4" aria-hidden /> Wprowadź zastępstwo i powiadom
          </Button>
          <ErrorBox error={add.error || del.error} />
        </div>
      </div>
      <ul className="divide-y divide-border border-t border-border text-sm">
        {data.length === 0 && <li className="px-5 py-3 text-muted">Brak zastępstw.</li>}
        {data.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
            <div className="min-w-0 flex-1">
              <span className="font-medium">{s.deputy_name}</span> zastępuje <span className="font-medium">{s.absent_name}</span>
              <div className="text-xs text-muted">
                {fmtDate(s.start)} – {fmtDate(s.end)}
                {s.note ? ` · ${s.note}` : ""}
              </div>
            </div>
            {s.active && <Badge tone="green">trwa</Badge>}
            <Button size="sm" variant="ghost" onClick={() => del.mutate(s.id)} aria-label="Zakończ zastępstwo">
              <Trash2 className="h-4 w-4" aria-hidden /> Usuń
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ------------------------------------------------------------------ historia ocen + oceny historyczne

interface HistoryRow {
  id: number;
  cycle_name: string;
  status: string;
  result: string | null;
  level: string | null;
  average: number | null;
  drawn_up: string | null;
  acknowledged_at: string | null;
  historical: boolean;
}

export function ReviewHistory({ employeeId }: { employeeId: number }) {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["hr-history", employeeId], queryFn: () => api<HistoryRow[]>(`/admin/employees/${employeeId}/reviews`) });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ drawn_up: "", acknowledged_at: "", result: "pozytywna", level: "na poziomie oczekiwań", average: "", note: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: () =>
      api<{ due_dates_changed: { due_date: string }[] }>(`/admin/employees/${employeeId}/historical-reviews`, {
        method: "POST",
        json: { ...f, acknowledged_at: f.acknowledged_at || null, average: f.average ? Number(f.average.replace(",", ".")) : null },
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["hr-history", employeeId] });
      qc.invalidateQueries({ queryKey: ["hr-employees"] });
      setOpen(false);
      setMsg(r.due_dates_changed.length ? `Zapisano. Termin bieżącej oceny przeliczony: ${fmtDate(r.due_dates_changed[0].due_date)}.` : "Zapisano ocenę historyczną.");
    },
  });
  return (
    <div className="space-y-2 text-sm">
      <h3 className="flex items-center gap-1.5 font-semibold">
        <History className="h-4 w-4" aria-hidden /> Historia ocen
      </h3>
      <ul className="space-y-1">
        {data.length === 0 && <li className="text-muted">Brak sporządzonych ocen.</li>}
        {data.map((h) => (
          <li key={h.id} className="flex flex-wrap items-center gap-2 rounded-md bg-slate-50 px-3 py-1.5">
            {h.historical ? <span>ocena historyczna</span> : <Link href={`/reviews/${h.id}`} className="text-primary hover:underline">{h.cycle_name}</Link>}
            <span className="text-muted">sporządzona {fmtDate(h.drawn_up)}</span>
            {h.result && <Badge tone={h.result === "pozytywna" ? "green" : "red"}>{h.result}</Badge>}
            {h.level && <span className="text-xs text-slate-600">{h.level}</span>}
            {!h.historical && <Badge tone={statusTone(h.status)}>{STATUS_LABEL[h.status]}</Badge>}
          </li>
        ))}
      </ul>
      {msg && <p className="rounded-md bg-blue-50 px-3 py-2 text-blue-900">{msg}</p>}
      {!open ? (
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" aria-hidden /> Wprowadź ocenę historyczną
        </Button>
      ) : (
        <div className="space-y-2 rounded-md border border-border p-3">
          <p className="text-xs text-muted">Ocena sprzed wdrożenia systemu (z akt osobowych). Od niej liczą się terminy kolejnej oceny, art. 71 i art. 89 ustawy.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <Label htmlFor="hd">Data sporządzenia</Label>
              <Input id="hd" type="date" value={f.drawn_up} onChange={(e) => setF({ ...f, drawn_up: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="ha">Data zapoznania (opcjonalnie)</Label>
              <Input id="ha" type="date" value={f.acknowledged_at} onChange={(e) => setF({ ...f, acknowledged_at: e.target.value })} />
            </div>
            <div>
              <Label htmlFor="hr">Ocena</Label>
              <select id="hr" className={select} value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}>
                <option value="pozytywna">pozytywna</option>
                <option value="negatywna">negatywna</option>
              </select>
            </div>
            <div>
              <Label htmlFor="hl">Poziom</Label>
              <select id="hl" className={select} value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })}>
                {SCALE.map((s) => (
                  <option key={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="hs">Średnia (opcjonalnie)</Label>
              <Input id="hs" inputMode="decimal" value={f.average} onChange={(e) => setF({ ...f, average: e.target.value })} placeholder="np. 6,4" />
            </div>
            <div>
              <Label htmlFor="hn">Uwagi / sygnatura</Label>
              <Input id="hn" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="np. teczka akt, nr dokumentu" />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => add.mutate()} disabled={!f.drawn_up} loading={add.isPending}>
              Zapisz
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Anuluj
            </Button>
          </div>
          <ErrorBox error={add.error} />
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ import z systemu kadrowego

interface ImportRow {
  row: number;
  full_name: string;
  position: string;
  department: string;
  manager: string | null;
  sheet_type: string;
  contract_type: string | null;
  employment_start: string | null;
  email: string | null;
  errors: string[];
  warnings: string[];
}

export function ImportPanel() {
  const qc = useQueryClient();
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<{ dry_run: boolean; rows: ImportRow[]; valid: number; created: number } | null>(null);
  const run = useMutation({
    mutationFn: (dry_run: boolean) => api<typeof result & object>("/admin/import/employees", { method: "POST", json: { csv, dry_run } }),
    onSuccess: (r) => {
      setResult(r);
      if (!r.dry_run) qc.invalidateQueries({ queryKey: ["hr-employees"] });
    },
  });
  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Upload className="h-4 w-4 text-primary" aria-hidden /> Import z systemu kadrowego
          </span>
        }
        subtitle="Wklej plik CSV wyeksportowany z systemu kadrowego. Najpierw weryfikacja, potem zapis tylko poprawnych wierszy."
      />
      <div className="space-y-3 p-5 text-sm">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => downloadFile("/admin/import/template.csv", "import_pracownikow_wzor.csv")}>
            <Download className="h-4 w-4" aria-hidden /> Wzór pliku CSV
          </Button>
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1 text-sm hover:bg-slate-50">
            <FileSpreadsheet className="h-4 w-4" aria-hidden /> Wczytaj plik
            <input type="file" accept=".csv,text/csv" className="sr-only" onChange={async (e) => setCsv(await (e.target.files?.[0]?.text() ?? Promise.resolve("")))} />
          </label>
        </div>
        <Textarea rows={6} value={csv} onChange={(e) => setCsv(e.target.value)} className="font-mono text-xs" placeholder="imie_nazwisko;stanowisko;komorka;przelozony;arkusz;podstawa_zatrudnienia;data_zatrudnienia;email" aria-label="Dane CSV" />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => run.mutate(true)} disabled={csv.trim().length < 10} loading={run.isPending}>
            Zweryfikuj dane
          </Button>
          {result?.dry_run && result.valid > 0 && (
            <Button onClick={() => run.mutate(false)} loading={run.isPending}>
              Zapisz {result.valid} poprawnych wierszy
            </Button>
          )}
        </div>
        <ErrorBox error={run.error} />
        {result && (
          <div className="overflow-x-auto">
            <p className="mb-2 font-medium">
              {result.dry_run ? `Weryfikacja: ${result.valid} z ${result.rows.length} wierszy poprawnych.` : `Zapisano ${result.created} pracowników.`}
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-left text-muted">
                  <th className="py-1 pr-2">Wiersz</th>
                  <th className="py-1 pr-2">Pracownik</th>
                  <th className="py-1 pr-2">Komórka / przełożony</th>
                  <th className="py-1 pr-2">Arkusz / zatrudnienie</th>
                  <th className="py-1">Weryfikacja</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.row} className={cn("border-b border-border align-top", r.errors.length > 0 && "bg-red-50")}>
                    <td className="py-1.5 pr-2">{r.row}</td>
                    <td className="py-1.5 pr-2">
                      {r.full_name}
                      <div className="text-muted">{r.position}</div>
                    </td>
                    <td className="py-1.5 pr-2">
                      {r.department}
                      <div className="text-muted">{r.manager ?? "-"}</div>
                    </td>
                    <td className="py-1.5 pr-2">
                      {r.sheet_type} · {r.contract_type ?? "?"}
                    </td>
                    <td className="py-1.5">
                      {r.errors.map((e) => (
                        <div key={e} className="text-red-700">
                          ✕ {e}
                        </div>
                      ))}
                      {r.warnings.map((w) => (
                        <div key={w} className="text-amber-800">
                          ! {w}
                        </div>
                      ))}
                      {!r.errors.length && !r.warnings.length && <span className="text-emerald-700">✓ poprawny</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ zestawienia

interface Stats {
  generated: string;
  k_anonymity: number;
  total: { n: number; hidden: boolean; results?: Record<string, number>; average?: number | null };
  departments: Record<string, { n: number; hidden: boolean; results?: Record<string, number>; average?: number | null }>;
  process: Record<string, number>;
}

const PROCESS_LABEL: Record<string, string> = {
  reviews_in_progress: "oceny w toku",
  overdue: "po terminie",
  due_next_60_days: "termin w ciągu 60 dni",
  objections: "sprzeciwy",
  promotion_requests: "wnioski o stopień służbowy",
  ack_fiction: "fikcje zapoznania",
};

export function ExportPanel() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { data: stats } = useQuery({ queryKey: ["hr-stats"], queryFn: () => api<Stats>("/admin/export/statistics") });
  const csv = () => {
    setErr(null);
    const q = new URLSearchParams();
    if (from) q.set("date_from", from);
    if (to) q.set("date_to", to);
    downloadFile(`/admin/export/reviews.csv?${q}`, `oceny_okresowe_${new Date().toISOString().slice(0, 10)}.csv`).catch((e) => setErr(String(e.message)));
  };
  const json = () =>
    api<Stats>("/admin/export/statistics").then((s) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(s, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `sprawozdanie_oceny_${s.generated}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader title="Zestawienie do archiwizacji lub kontroli" subtitle="Wszystkie sporządzone oceny z datami, ocenami cząstkowymi, uzasadnieniem, wnioskami do IPR i sprzeciwami (CSV, otwiera się w Excelu)." />
        <div className="space-y-3 p-5 text-sm">
          <div className="flex flex-wrap gap-2">
            <div>
              <Label htmlFor="ef">Sporządzone od</Label>
              <Input id="ef" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="et">do</Label>
              <Input id="et" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
          </div>
          <Button onClick={csv}>
            <Download className="h-4 w-4" aria-hidden /> Pobierz zestawienie CSV
          </Button>
          {err && <p className="text-red-700">{err}</p>}
          <p className="text-xs text-muted">Pobranie jest zapisywane w dzienniku zdarzeń (dane osobowe).</p>
        </div>
      </Card>
      <Card>
        <CardHeader title="Zestawienie na potrzeby sprawozdawczości" subtitle={`Dane zagregowane - grupy mniejsze niż ${stats?.k_anonymity ?? 5} osób są ukryte. Format JSON do systemu sprawozdawczego.`} />
        <div className="space-y-3 p-5 text-sm">
          {stats && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Object.entries(stats.process).map(([k, v]) => (
                  <div key={k} className="rounded-md bg-slate-50 px-3 py-2">
                    <div className="text-lg font-semibold">{v}</div>
                    <div className="text-xs text-muted">{PROCESS_LABEL[k] ?? k}</div>
                  </div>
                ))}
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-left text-muted">
                    <th className="py-1">Komórka</th>
                    <th className="py-1">Ocen</th>
                    <th className="py-1">Pozytywne / negatywne</th>
                    <th className="py-1">Średnia</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(stats.departments).map(([name, d]) => (
                    <tr key={name} className="border-b border-border">
                      <td className="py-1">{name}</td>
                      <td className="py-1">{d.n}</td>
                      <td className="py-1">{d.hidden ? "ukryte (k-anonimowość)" : `${d.results?.pozytywna ?? 0} / ${d.results?.negatywna ?? 0}`}</td>
                      <td className="py-1">{d.hidden ? "-" : (d.average?.toFixed(2) ?? "-")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <Button variant="secondary" onClick={json}>
            <Download className="h-4 w-4" aria-hidden /> Pobierz zestawienie JSON
          </Button>
        </div>
      </Card>
    </div>
  );
}
