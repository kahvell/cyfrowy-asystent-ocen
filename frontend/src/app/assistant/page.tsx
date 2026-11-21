"use client";

import { useMutation } from "@tanstack/react-query";
import { BookOpen, Send } from "lucide-react";
import { useState, type FormEvent } from "react";
import { AiLabel, AiWaiting, Button, Card, ErrorBox, Input, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { modelLabel } from "@/lib/utils";

interface Answer {
  answer: string;
  citations: { ref: string; text: string; source: string }[];
  model: string;
}

const EXAMPLES = [
  "Czy muszę pisać uzasadnienie oceny pozytywnej?",
  "Ile kryteriów dodatkowych mogę wybrać?",
  "Kiedy ocena jest negatywna?",
  "Co omawiamy podczas rozmowy oceniającej?",
  "Ile dni ma pracownik na sprzeciw od oceny?",
];

export default function AssistantPage() {
  const [q, setQ] = useState("");
  const [history, setHistory] = useState<{ q: string; a: Answer }[]>([]);
  const ask = useMutation({
    mutationFn: (question: string) => api<Answer>("/assistant/legal-qa", { method: "POST", json: { question } }),
    onSuccess: (a, question) => {
      setHistory((h) => [{ q: question, a }, ...h]);
      setQ("");
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length >= 3) ask.mutate(q.trim());
  };

  return (
    <>
      <PageTitle title="Asystent przepisów" subtitle="Odpowiedzi wyłącznie na podstawie rozporządzenia PRM z 4.04.2016 r. (Dz.U. 2016 poz. 470) - z cytatem źródła." />
      <Card className="p-5">
        <form onSubmit={submit} className="flex gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Zadaj pytanie o ocenę okresową…" aria-label="Pytanie" />
          <Button type="submit" loading={ask.isPending}>
            <Send className="h-4 w-4" aria-hidden /> Zapytaj
          </Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => ask.mutate(ex)} className="rounded-full border border-border px-2.5 py-1 text-xs hover:bg-slate-50">
              {ex}
            </button>
          ))}
        </div>
        <div className="mt-3">
          <AiWaiting active={ask.isPending} typical="40–90 s" />
          <ErrorBox error={ask.error} />
        </div>
      </Card>
      <div className="mt-6 space-y-4">
        {history.map(({ q, a }, i) => (
          <Card key={i} className="p-5">
            <p className="font-medium">{q}</p>
            <p className="mt-2 whitespace-pre-line text-sm text-slate-700">{a.answer}</p>
            <div className="mt-3 space-y-2">
              {a.citations.map((c) => (
                <details key={c.ref} className="rounded-md bg-slate-50 p-2 text-sm">
                  <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-primary">
                    <BookOpen className="h-4 w-4" aria-hidden /> {c.ref}
                  </summary>
                  <p className="mt-1 text-slate-700">{c.text}</p>
                  <p className="mt-1 text-xs text-muted">{c.source}</p>
                </details>
              ))}
            </div>
            <div className="mt-3">
              <AiLabel model={modelLabel(a.model)} />
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
