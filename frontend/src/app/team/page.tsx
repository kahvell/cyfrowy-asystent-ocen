"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, NotebookPen } from "lucide-react";
import Link from "next/link";
import { useMe } from "@/components/app-shell";
import { RiskBadge, type TeamSignal } from "@/components/hr-partner";
import { Reminders } from "@/components/reminders";
import { Badge, Card, ErrorBox, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { TeamMember } from "@/lib/types";
import { fmtDate, STATUS_LABEL, statusTone } from "@/lib/utils";

export default function TeamPage() {
  const me = useMe();
  const isAdmin = me?.role === "admin";
  // administrator widzi wszystkich pracowników (tryb korekty błędów w każdym arkuszu)
  const { data, error, isPending } = useQuery({
    queryKey: ["team", isAdmin],
    queryFn: () => api<TeamMember[]>(`/employees?team=${isAdmin ? "all" : "mine"}`),
  });
  const { data: signals } = useQuery({ queryKey: ["team-hr"], queryFn: () => api<TeamSignal[]>("/team/hr-partner"), enabled: me?.role === "manager" });
  const signalOf = (id: number) => signals?.find((s) => s.employee_id === id);

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const reminders = data.filter((e) => e.reminder);

  return (
    <>
      <PageTitle
        title={isAdmin ? "Wszyscy pracownicy" : "Mój zespół"}
        subtitle={
          isAdmin
            ? "Widok administratora: otwórz arkusz, aby skorzystać z trybu korekty błędów."
            : "Dziennik obserwacji prowadzony przez cały okres oceny chroni przed oceną „z ostatnich dwóch tygodni”."
        }
      />
      <Reminders />
      {reminders.length > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <span>
            Brak obserwacji od ponad 3 miesięcy: <strong>{reminders.map((r) => r.full_name).join(", ")}</strong>. Dodaj krótką notatkę - wystarczy jedno zdanie.
          </span>
        </div>
      )}
      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-5 py-3 font-medium">Pracownik</th>
              <th className="px-5 py-3 font-medium">Notatki</th>
              <th className="px-5 py-3 font-medium">Ostatnia obserwacja</th>
              <th className="px-5 py-3 font-medium">Ocena okresowa</th>
              <th className="px-5 py-3 font-medium">HR partner</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {data.map((e) => (
              <tr key={e.id} className="border-b border-border last:border-0 hover:bg-slate-50">
                <td className="px-5 py-3">
                  <Link href={`/employees/${e.id}`} className="font-medium text-primary hover:underline">
                    {e.full_name}
                  </Link>
                  <div className="text-xs text-muted">{e.position}</div>
                </td>
                <td className="px-5 py-3">
                  <span className="inline-flex items-center gap-1">
                    <NotebookPen className="h-4 w-4 text-muted" aria-hidden /> {e.notes_count}
                  </span>
                </td>
                <td className="px-5 py-3">
                  {fmtDate(e.last_note_date)} {e.reminder && <Badge tone="amber">przypomnienie</Badge>}
                </td>
                <td className="px-5 py-3">
                  {e.current_review ? (
                    <Link href={`/reviews/${e.current_review.id}`}>
                      <Badge tone={statusTone(e.current_review.status)}>{STATUS_LABEL[e.current_review.status]}</Badge>
                    </Link>
                  ) : (
                    <span className="text-xs text-muted">nie rozpoczęta</span>
                  )}
                </td>
                <td className="px-5 py-3">
                  <RiskBadge s={signalOf(e.id)} />
                </td>
                <td className="px-5 py-3 text-right">
                  <Link href={`/employees/${e.id}`} aria-label={`Otwórz ${e.full_name}`}>
                    <ChevronRight className="h-4 w-4 text-muted" />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
