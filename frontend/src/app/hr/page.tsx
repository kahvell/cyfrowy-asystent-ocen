"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownUp, CalendarX2, Plus, Search, Trash2, UserMinus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Label, PageTitle, Spinner, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { cn, fmtDate, STATUS_LABEL, statusTone } from "@/lib/utils";

interface HrEmployee {
  id: number;
  full_name: string;
  position: string;
  department_id: number;
  department: string;
  manager_id: number | null;
  manager_name: string | null;
  sheet_type: string;
  is_civil_servant: boolean;
  employment_start: string | null;
  employment_end: string | null;
  appointment_year: number | null;
  civil_grade: number | null;
  civil_grade_date: string | null;
  position_description: string;
  active: boolean;
  senior_position: boolean;
  email: string | null;
  role: string | null;
  review: { id: number; status: string; due_date: string | null } | null;
}

interface Structure {
  departments: { id: number; name: string }[];
  managers: { id: number; full_name: string; position: string }[];
}

interface Absences {
  absences: { id: number; start: string; end: string; kind: string; days: number }[];
  continuous: { start: string; end: string; days: number; extends_deadline: boolean }[];
}

type SortKey = "full_name" | "department" | "manager_name" | "due";

const select = "w-full rounded-md border border-border bg-white px-3 py-2 text-sm";

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["hr-employees"] });
    qc.invalidateQueries({ queryKey: ["reminders"] });
  };
}

function EmployeeForm({ emp, structure, onDone }: { emp?: HrEmployee; structure: Structure; onDone: (msg?: string) => void }) {
  const invalidate = useInvalidate();
  const [f, setF] = useState({
    full_name: emp?.full_name ?? "",
    position: emp?.position ?? "",
    department_id: emp?.department_id ?? structure.departments[0]?.id ?? 0,
    manager_id: emp?.manager_id ?? null,
    sheet_type: emp?.sheet_type ?? "C",
    is_civil_servant: emp?.is_civil_servant ?? false,
    employment_start: emp?.employment_start ?? "",
    appointment_year: emp?.appointment_year ?? null,
    civil_grade: emp?.civil_grade ?? null,
    civil_grade_date: emp?.civil_grade_date ?? "",
    position_description: emp?.position_description ?? "",
    senior_position: emp?.senior_position ?? false,
    email: "",
    reason: "",
    significant_change_date: "",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF({ ...f, [k]: v });
  const save = useMutation<{
    reviews_moved?: number[];
    initial_password?: string | null;
    position_change?: { effect: string; criteria_deadline?: string; due_date?: string }[];
  }>({
    mutationFn: () => {
      const json = {
        ...f,
        employment_start: f.employment_start || null,
        civil_grade_date: f.civil_grade_date || null,
        email: f.email || undefined,
        significant_change_date: f.significant_change_date || undefined,
      };
      return emp
        ? api<{ reviews_moved?: number[]; position_change?: { effect: string; criteria_deadline?: string; due_date?: string }[] }>(`/admin/employees/${emp.id}`, {
            method: "PATCH",
            json: { ...json, email: undefined },
          })
        : api<{ initial_password?: string | null }>("/admin/employees", { method: "POST", json: { ...json, reason: undefined, significant_change_date: undefined } });
    },
    onSuccess: (r) => {
      invalidate();
      const moved = r.reviews_moved?.length ? `Zmiana oceniającego: przeniesiono ${r.reviews_moved.length} trwającą ocenę do nowego przełożonego.` : undefined;
      const pwd = r.initial_password ? `Konto utworzone. Hasło startowe: ${r.initial_password} (przekaż je bezpiecznym kanałem).` : undefined;
      const pc = r.position_change?.[0];
      const change = pc
        ? pc.effect === "criteria_reopened"
          ? `Zmiana stanowiska w ciągu 6 mies.: ponowna rozmowa i kryteria do ${fmtDate(pc.criteria_deadline)}, termin oceny bez zmian (§ 9 ust. 1).`
          : `Zmiana stanowiska: ocena okresowa do ${fmtDate(pc.due_date)} (art. 81 ust. 6, § 9 ust. 2).`
        : undefined;
      onDone(change ?? moved ?? pwd ?? "Zapisano.");
    },
  });
  const managerChanged = emp && f.manager_id !== emp.manager_id;
  const positionChanged = emp && (f.position !== emp.position || f.position_description !== emp.position_description);

  return (
    <form
      className="grid gap-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div>
        <Label htmlFor="fn">Imię i nazwisko</Label>
        <Input id="fn" required value={f.full_name} onChange={(e) => set("full_name", e.target.value)} />
      </div>
      <div>
        <Label htmlFor="pos">Stanowisko</Label>
        <Input id="pos" required value={f.position} onChange={(e) => set("position", e.target.value)} />
      </div>
      <div>
        <Label htmlFor="dep">Komórka organizacyjna</Label>
        <select id="dep" className={select} value={f.department_id} onChange={(e) => set("department_id", Number(e.target.value))}>
          {structure.departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <Label htmlFor="mgr">Bezpośredni przełożony (oceniający)</Label>
        <select id="mgr" className={select} value={f.manager_id ?? ""} onChange={(e) => set("manager_id", e.target.value ? Number(e.target.value) : null)}>
          <option value="">- brak -</option>
          {structure.managers
            .filter((m) => m.id !== emp?.id)
            .map((m) => (
              <option key={m.id} value={m.id}>
                {m.full_name} · {m.position}
              </option>
            ))}
        </select>
      </div>
      {managerChanged && (
        <div className="sm:col-span-2">
          <Label htmlFor="reason">Powód zmiany podległości</Label>
          <Input id="reason" value={f.reason} onChange={(e) => set("reason", e.target.value)} placeholder="np. zmiana struktury, przeniesienie" />
          <p className="mt-1 text-xs text-amber-800">Trwająca ocena przejdzie do nowego przełożonego (zmiana oceniającego, art. 81 ust. 8 pkt 1). Obie strony dostaną powiadomienie.</p>
        </div>
      )}
      {positionChanged && (
        <div className="sm:col-span-2">
          <Label htmlFor="chg">Data zmiany stanowiska - wypełnij, jeśli wiąże się z istotną zmianą zakresu obowiązków</Label>
          <Input id="chg" type="date" value={f.significant_change_date} onChange={(e) => set("significant_change_date", e.target.value)} className="w-auto" />
          <p className="mt-1 text-xs text-muted">
            W ciągu 6 mies. od ustalenia kryteriów lub ostatniej oceny: ponowna rozmowa i kryteria w 30 dni (§ 9 ust. 1). Później: ocena w związku ze zmianą
            stanowiska, od 7 dni przed do 30 dni po zmianie (art. 81 ust. 6, § 9 ust. 2).
          </p>
        </div>
      )}
      <div>
        <Label htmlFor="sheet">Arkusz oceny</Label>
        <select id="sheet" className={select} value={f.sheet_type} onChange={(e) => set("sheet_type", e.target.value)}>
          <option value="A">A - kierownik urzędu</option>
          <option value="B">B - bezpośrednie kierowanie pracownikami</option>
          <option value="C">C - pozostałe stanowiska</option>
        </select>
      </div>
      <div>
        <Label htmlFor="start">Nawiązanie stosunku pracy na czas nieokreślony / mianowanie</Label>
        <Input id="start" type="date" value={f.employment_start} onChange={(e) => set("employment_start", e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={f.is_civil_servant} onChange={(e) => set("is_civil_servant", e.target.checked)} /> urzędnik służby cywilnej (mianowany)
      </label>
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={f.senior_position} onChange={(e) => set("senior_position", e.target.checked)} /> wyższe stanowisko w służbie cywilnej
        (art. 52, np. dyrektor generalny, kierujący wydziałem w urzędzie wojewódzkim) - bez IPR (art. 108)
      </label>
      {f.is_civil_servant && (
        <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
          <div>
            <Label htmlFor="ay">Rok mianowania</Label>
            <Input id="ay" type="number" min={1996} value={f.appointment_year ?? ""} onChange={(e) => set("appointment_year", e.target.value ? Number(e.target.value) : null)} />
          </div>
          <div>
            <Label htmlFor="cg">Stopień służbowy</Label>
            <select id="cg" className={select} value={f.civil_grade ?? ""} onChange={(e) => set("civil_grade", e.target.value ? Number(e.target.value) : null)}>
              <option value="">-</option>
              {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => (
                <option key={g}>{g}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="cgd">Data przyznania stopnia</Label>
            <Input id="cgd" type="date" value={f.civil_grade_date} onChange={(e) => set("civil_grade_date", e.target.value)} />
          </div>
        </div>
      )}
      <div className="sm:col-span-2">
        <Label htmlFor="desc">Opis stanowiska (główne obowiązki)</Label>
        <Textarea id="desc" rows={2} value={f.position_description} onChange={(e) => set("position_description", e.target.value)} />
      </div>
      {!emp && (
        <div className="sm:col-span-2">
          <Label htmlFor="mail">E-mail służbowy (utworzy konto w systemie)</Label>
          <Input id="mail" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} placeholder="opcjonalnie" />
        </div>
      )}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" loading={save.isPending}>
          {emp ? "Zapisz zmiany" : "Dodaj pracownika"}
        </Button>
        <Button type="button" variant="ghost" onClick={() => onDone()}>
          Anuluj
        </Button>
      </div>
      <div className="sm:col-span-2">
        <ErrorBox error={save.error} />
      </div>
    </form>
  );
}

function AbsencesPanel({ emp }: { emp: HrEmployee }) {
  const qc = useQueryClient();
  const invalidate = useInvalidate();
  const { data } = useQuery({ queryKey: ["absences", emp.id], queryFn: () => api<Absences>(`/admin/employees/${emp.id}/absences`) });
  const [f, setF] = useState({ start: "", end: "", kind: "zwolnienie lekarskie" });
  const [msg, setMsg] = useState<string | null>(null);
  const done = (r: { due_dates_changed: { from: string | null; to: string }[] }) => {
    qc.invalidateQueries({ queryKey: ["absences", emp.id] });
    invalidate();
    setMsg(r.due_dates_changed.length ? `Termin oceny przesunięty: ${fmtDate(r.due_dates_changed[0].from)} → ${fmtDate(r.due_dates_changed[0].to)} (art. 81 ust. 7).` : "Zapisano. Termin oceny bez zmian.");
  };
  const add = useMutation({
    mutationFn: () => api<{ due_dates_changed: { from: string | null; to: string }[] }>(`/admin/employees/${emp.id}/absences`, { method: "POST", json: f }),
    onSuccess: done,
  });
  const del = useMutation({
    mutationFn: (id: number) => api<{ due_dates_changed: { from: string | null; to: string }[] }>(`/admin/absences/${id}`, { method: "DELETE" }),
    onSuccess: done,
  });
  return (
    <div className="space-y-3 text-sm">
      <h3 className="flex items-center gap-1.5 font-semibold">
        <CalendarX2 className="h-4 w-4" aria-hidden /> Nieobecności usprawiedliwione
      </h3>
      <p className="text-xs text-muted">Następujące po sobie nieobecności są łączone (dni wolne ich nie przerywają). Nieobecność dłuższa niż miesiąc przedłuża termin oceny.</p>
      <ul className="space-y-1">
        {data?.absences.map((a) => (
          <li key={a.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-1.5">
            <span>
              {fmtDate(a.start)} – {fmtDate(a.end)} · {a.kind} · {a.days} dni
            </span>
            <button className="text-muted hover:text-red-700" aria-label="Usuń nieobecność" onClick={() => del.mutate(a.id)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </li>
        ))}
        {data && data.absences.length === 0 && <li className="text-muted">Brak.</li>}
      </ul>
      {data?.continuous.some((c) => c.extends_deadline) && (
        <p className="text-xs text-amber-800">
          Nieobecności ciągłe przedłużające termin:{" "}
          {data.continuous
            .filter((c) => c.extends_deadline)
            .map((c) => `${fmtDate(c.start)}–${fmtDate(c.end)} (${c.days} dni)`)
            .join(", ")}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <Input type="date" aria-label="Od" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} className="w-auto" />
        <Input type="date" aria-label="Do" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} className="w-auto" />
        <select aria-label="Rodzaj" className="rounded-md border border-border px-2 py-2 text-sm" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          {["zwolnienie lekarskie", "urlop wypoczynkowy", "urlop związany z rodzicielstwem", "inna usprawiedliwiona"].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <Button size="sm" onClick={() => add.mutate()} disabled={!f.start || !f.end} loading={add.isPending}>
          Dodaj
        </Button>
      </div>
      {msg && <p className="rounded-md bg-blue-50 px-3 py-2 text-blue-900">{msg}</p>}
      <ErrorBox error={add.error || del.error} />
    </div>
  );
}

function EmployeeDetail({ emp, structure, onClose }: { emp: HrEmployee; structure: Structure; onClose: (msg?: string) => void }) {
  const invalidate = useInvalidate();
  const [end, setEnd] = useState("");
  const [askReview, setAskReview] = useState(false);
  const terminate = useMutation({
    mutationFn: () =>
      api<{ notes_deleted: number; review_requested?: boolean }>(`/admin/employees/${emp.id}/terminate`, {
        method: "POST",
        json: { employment_end: end, review_requested: askReview },
      }),
    onSuccess: (r) => {
      invalidate();
      onClose(
        r.review_requested
          ? "Przekazano przełożonemu wniosek o ocenę okresową odchodzącego pracownika. Zakończ zatrudnienie po sporządzeniu oceny."
          : `Zakończono zatrudnienie. Oceny zostają w dokumentacji, usunięto ${r.notes_deleted} roboczych notatek przełożonego.`,
      );
    },
  });
  const remove = useMutation({
    mutationFn: () => api(`/admin/employees/${emp.id}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      onClose("Usunięto dane pracownika.");
    },
  });
  return (
    <Card>
      <CardHeader
        title={emp.full_name}
        subtitle={`${emp.position} · ${emp.department}${emp.email ? ` · konto: ${emp.email}` : " · bez konta"}`}
        action={
          emp.review && (
            <Link href={`/reviews/${emp.review.id}`} className="text-sm text-primary hover:underline">
              arkusz oceny →
            </Link>
          )
        }
      />
      <div className="grid gap-6 p-5 lg:grid-cols-[1fr_380px]">
        <EmployeeForm key={emp.id} emp={emp} structure={structure} onDone={onClose} />
        <div className="space-y-6">
          <AbsencesPanel emp={emp} />
          {emp.active && (
            <div className="space-y-2 border-t border-border pt-4 text-sm">
              <h3 className="flex items-center gap-1.5 font-semibold">
                <UserMinus className="h-4 w-4" aria-hidden /> Ustanie zatrudnienia
              </h3>
              <p className="text-xs text-muted">Sporządzone oceny zostają w dokumentacji pracowniczej, robocze notatki przełożonego są usuwane, konto blokowane.</p>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={askReview} onChange={(e) => setAskReview(e.target.checked)} /> pracownik wnioskuje o ocenę okresową przed odejściem
                (Standardy ZZL, rozdz. VII pkt 3)
              </label>
              <div className="flex gap-2">
                <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-auto" aria-label="Data ustania zatrudnienia" />
                <Button size="sm" variant="danger" disabled={!end} onClick={() => terminate.mutate()} loading={terminate.isPending}>
                  {askReview ? "Przekaż wniosek o ocenę" : "Zakończ zatrudnienie"}
                </Button>
              </div>
              <Button size="sm" variant="ghost" onClick={() => confirm(`Usunąć dane: ${emp.full_name}? Tylko dla danych wprowadzonych omyłkowo.`) && remove.mutate()}>
                <Trash2 className="h-4 w-4" aria-hidden /> Usuń (dane wprowadzone omyłkowo)
              </Button>
              <ErrorBox error={terminate.error || remove.error} />
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

export default function HrPage() {
  const [q, setQ] = useState("");
  const [inactive, setInactive] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "full_name", dir: 1 });
  const [selected, setSelected] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const { data, error, isPending } = useQuery({
    queryKey: ["hr-employees", q, inactive],
    queryFn: () => api<HrEmployee[]>(`/admin/employees?q=${encodeURIComponent(q)}&include_inactive=${inactive}`),
  });
  const { data: structure } = useQuery({ queryKey: ["hr-structure"], queryFn: () => api<Structure>("/admin/structure") });

  const value = (e: HrEmployee, k: SortKey) => (k === "due" ? (e.review?.due_date ?? "9999") : (e[k] ?? ""));
  const rows = [...(data ?? [])].sort((a, b) => String(value(a, sort.key)).localeCompare(String(value(b, sort.key)), "pl") * sort.dir);
  const current = rows.find((e) => e.id === selected);
  const th = (key: SortKey, label: string) => (
    <th className="px-4 py-3 font-medium" aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => setSort({ key, dir: sort.key === key ? ((-sort.dir) as 1 | -1) : 1 })}>
        {label} <ArrowDownUp className="h-3 w-3" aria-hidden />
      </button>
    </th>
  );
  const close = (m?: string) => {
    setSelected(null);
    setAdding(false);
    if (m) setMsg(m);
  };

  return (
    <>
      <PageTitle
        title="Kadry"
        subtitle="Dane pracowników, podległość służbowa (kto kogo ocenia), nieobecności i zatrudnienie. Bez dostępu do dziennika obserwacji i szkiców ocen."
        action={
          <Button onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" aria-hidden /> Dodaj pracownika
          </Button>
        }
      />
      {msg && (
        <p className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900" role="status">
          {msg}
        </p>
      )}
      {adding && structure && (
        <Card className="mb-6">
          <CardHeader title="Nowy pracownik" subtitle="Arkusz dobierz do stanowiska; termin pierwszej oceny wyliczy się od daty nawiązania stosunku pracy." />
          <div className="p-5">
            <EmployeeForm structure={structure} onDone={close} />
          </div>
        </Card>
      )}
      {current && structure && (
        <div className="mb-6">
          <EmployeeDetail key={current.id} emp={current} structure={structure} onClose={close} />
        </div>
      )}
      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Szukaj: nazwisko, stanowisko, komórka…" className="pl-9" aria-label="Szukaj pracownika" />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> pokaż byłych pracowników
          </label>
          <span className="text-sm text-muted">{rows.length} osób</span>
        </div>
        {isPending ? (
          <Spinner />
        ) : error ? (
          <ErrorBox error={error} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                  {th("full_name", "Pracownik")}
                  {th("department", "Komórka")}
                  {th("manager_name", "Oceniający")}
                  <th className="px-4 py-3 font-medium">Arkusz</th>
                  <th className="px-4 py-3 font-medium">Ocena okresowa</th>
                  {th("due", "Termin oceny")}
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id} className={cn("cursor-pointer border-b border-border last:border-0 hover:bg-slate-50", selected === e.id && "bg-blue-50", !e.active && "opacity-60")} onClick={() => setSelected(e.id)}>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-primary">{e.full_name}</div>
                      <div className="text-xs text-muted">
                        {e.position}
                        {e.is_civil_servant ? " · urzędnik" : ""}
                        {!e.active && ` · zatrudnienie do ${fmtDate(e.employment_end)}`}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">{e.department}</td>
                    <td className="px-4 py-2.5">{e.manager_name ?? "-"}</td>
                    <td className="px-4 py-2.5">{e.sheet_type}</td>
                    <td className="px-4 py-2.5">{e.review ? <Badge tone={statusTone(e.review.status)}>{STATUS_LABEL[e.review.status]}</Badge> : <span className="text-xs text-muted">brak</span>}</td>
                    <td className="px-4 py-2.5">{e.review && !["final", "acknowledged", "objection"].includes(e.review.status) ? fmtDate(e.review.due_date) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
