"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Criterion, Note } from "@/lib/types";
import { cn, fmtDate } from "@/lib/utils";
import { Badge, Button, Card, CardHeader, ErrorBox, Input, Sentiment, Spinner, Textarea } from "./ui";

export function useCriteria() {
  return useQuery({ queryKey: ["criteria"], queryFn: () => api<Criterion[]>("/criteria"), staleTime: Infinity });
}

export function NoteComposer({ employeeId, placeholder }: { employeeId: number; placeholder?: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const add = useMutation({
    mutationFn: () => api<Note>(`/employees/${employeeId}/notes`, { method: "POST", json: { text, date } }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["notes", employeeId] });
      qc.invalidateQueries({ queryKey: ["team"] });
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim().length >= 3) add.mutate();
      }}
      className="space-y-2"
    >
      <Textarea
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder ?? "Co konkretnie się wydarzyło? Np. „Poprowadził spotkanie z wykonawcą, ustalił harmonogram i rozesłał notatkę w 2 h”."}
        aria-label="Treść obserwacji"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Input type="date" value={date} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} className="w-auto" aria-label="Data" />
        <Button type="submit" loading={add.isPending} disabled={text.trim().length < 3}>
          <Plus className="h-4 w-4" aria-hidden /> Dodaj obserwację
        </Button>
        <span className="text-xs text-muted">
          <Sparkles className="inline h-3 w-3 text-ai" aria-hidden /> AI przypisze kryteria i wydźwięk - możesz je poprawić.
        </span>
      </div>
      <ErrorBox error={add.error} />
    </form>
  );
}

function TagEditor({ note, onDone }: { note: Note; onDone: () => void }) {
  const qc = useQueryClient();
  const { data: criteria } = useCriteria();
  const [selected, setSelected] = useState<number[]>(note.criteria.map((c) => c.criterion_id));
  const save = useMutation({
    mutationFn: () => api<Note>(`/notes/${note.id}/criteria`, { method: "PATCH", json: { criterion_ids: selected } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes", note.employee_id] });
      onDone();
    },
  });
  return (
    <div className="mt-2 rounded-md border border-border bg-slate-50 p-3">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {criteria?.map((c) => {
          const on = selected.includes(c.id);
          return (
            <button
              key={c.id}
              type="button"
              aria-pressed={on}
              onClick={() => setSelected(on ? selected.filter((x) => x !== c.id) : [...selected, c.id])}
              className={cn(
                "rounded-full border px-2 py-0.5 text-xs",
                on ? "border-primary bg-primary text-white" : "border-border bg-white text-slate-700 hover:bg-slate-100",
              )}
            >
              {c.name}
            </button>
          );
        })}
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => save.mutate()} loading={save.isPending}>
          Zapisz kryteria
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Anuluj
        </Button>
      </div>
    </div>
  );
}

export function NoteItem({ note, highlighted, canEdit, canDelete }: { note: Note; highlighted?: boolean; canEdit?: boolean; canDelete?: boolean }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const del = useMutation({
    mutationFn: () => api(`/notes/${note.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notes", note.employee_id] }),
  });
  return (
    <li id={`note-${note.id}`} className={cn("px-5 py-3", highlighted && "note-highlight")}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="font-medium text-slate-700">{fmtDate(note.date)}</span>
        <Sentiment value={note.classified ? note.sentiment : null} />
        {note.source === "self" && <Badge tone="blue">od pracownika</Badge>}
        <span>#{note.id}</span>
        {note.author_name && <span>· {note.author_name}</span>}
      </div>
      <p className="mt-1 text-sm">{note.text}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {note.criteria.map((t) => (
          <Badge
            key={t.criterion_id}
            tone={t.assigned_by === "ai" ? "violet" : "slate"}
            title={t.assigned_by === "ai" ? `Przypisane przez AI (pewność ${Math.round(t.confidence * 100)}%)` : "Przypisane przez człowieka"}
          >
            {t.assigned_by === "ai" && <Sparkles className="h-3 w-3" aria-hidden />}
            {t.name}
          </Badge>
        ))}
        {note.classified && note.criteria.length === 0 && <span className="text-xs text-muted">brak przypisanych kryteriów</span>}
        {canEdit && !editing && (
          <button onClick={() => setEditing(true)} className="ml-1 inline-flex items-center gap-1 text-xs text-primary hover:underline">
            <Pencil className="h-3 w-3" aria-hidden /> popraw kryteria
          </button>
        )}
        {canDelete && (
          <button
            onClick={() => confirm("Usunąć notatkę?") && del.mutate()}
            className="ml-1 inline-flex items-center gap-1 text-xs text-red-700 hover:underline"
          >
            <Trash2 className="h-3 w-3" aria-hidden /> usuń
          </button>
        )}
      </div>
      {editing && <TagEditor note={note} onDone={() => setEditing(false)} />}
    </li>
  );
}

export function NotesList({
  employeeId,
  canEdit,
  myUserId,
  criterionFilter,
}: {
  employeeId: number;
  canEdit: boolean;
  myUserId?: number;
  criterionFilter?: number | null;
}) {
  const { data: criteria } = useCriteria();
  const [filter, setFilter] = useState<number | null>(criterionFilter ?? null);
  const { data, isPending, error } = useQuery({
    queryKey: ["notes", employeeId],
    queryFn: () => api<Note[]>(`/employees/${employeeId}/notes`),
    // dopóki AI klasyfikuje świeże notatki - odświeżaj
    refetchInterval: (q) => (q.state.data?.some((n) => !n.classified) ? 2500 : false),
  });
  const notes = (data ?? []).filter((n) => !filter || n.criteria.some((c) => c.criterion_id === filter));
  return (
    <Card>
      <CardHeader
        title="Dziennik obserwacji"
        subtitle={data ? `${data.length} notatek` : undefined}
        action={
          <div className="flex items-center gap-1">
            <select
              aria-label="Filtruj wg kryterium"
              className="rounded-md border border-border bg-white px-2 py-1 text-sm"
              value={filter ?? ""}
              onChange={(e) => setFilter(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Wszystkie kryteria</option>
              {criteria?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            {filter && (
              <button onClick={() => setFilter(null)} aria-label="Wyczyść filtr" className="p-1">
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        }
      />
      {isPending ? (
        <Spinner />
      ) : error ? (
        <div className="p-4">
          <ErrorBox error={error} />
        </div>
      ) : notes.length === 0 ? (
        <p className="p-5 text-sm text-muted">Brak notatek.</p>
      ) : (
        <ul className="divide-y divide-border">
          {notes.map((n) => (
            <NoteItem key={n.id} note={n} canEdit={canEdit} canDelete={!!myUserId && n.author_id === myUserId} />
          ))}
        </ul>
      )}
    </Card>
  );
}
