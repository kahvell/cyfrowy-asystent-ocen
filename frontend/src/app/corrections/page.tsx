"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Card, ErrorBox, Input, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, STATUS_LABEL, statusTone } from "@/lib/utils";

type ReviewRow = {
  id: number;
  status: keyof typeof STATUS_LABEL;
  employee_id: number;
  employee_name: string;
  cycle_name: string;
  due_date: string | null;
};

/** Administrator (schemat procesu KPRM): zakłada konta i poprawia błędy w polach zablokowanych na danym etapie.
 *  Nie widzi dziennika obserwacji, samooceny ani szkiców ocen - tylko listę arkuszy do trybu korekty. */
export default function CorrectionsPage() {
  const [q, setQ] = useState("");
  const { data, error, isPending } = useQuery({ queryKey: ["reviews-admin"], queryFn: () => api<ReviewRow[]>("/reviews") });

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const needle = q.trim().toLowerCase();
  const rows = data.filter((r) => !needle || r.employee_name.toLowerCase().includes(needle));

  return (
    <>
      <PageTitle
        title="Korekty arkuszy"
        subtitle="Tryb korekty błędów: zmiana pól zablokowanych na danym etapie, zawsze z podaniem powodu. Każda korekta trafia do historii arkusza, a oceniany i oceniający dostają powiadomienie."
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Szukaj pracownika" className="pl-9" aria-label="Szukaj pracownika" />
        </div>
        <p className="text-xs text-muted">
          Administrator nie ma wglądu w dziennik obserwacji, samoocenę ani szkice ocen (minimalizacja danych, art. 5 RODO).
        </p>
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-5 py-3 font-medium">Oceniany</th>
              <th className="px-5 py-3 font-medium">Cykl</th>
              <th className="px-5 py-3 font-medium">Etap</th>
              <th className="px-5 py-3 font-medium">Termin oceny</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border last:border-0 hover:bg-slate-50">
                <td className="px-5 py-3 font-medium">{r.employee_name}</td>
                <td className="px-5 py-3 text-muted">{r.cycle_name}</td>
                <td className="px-5 py-3">
                  <Badge tone={statusTone(r.status)}>{STATUS_LABEL[r.status]}</Badge>
                </td>
                <td className="px-5 py-3 text-muted">{fmtDate(r.due_date)}</td>
                <td className="px-5 py-3 text-right">
                  <Link href={`/reviews/${r.id}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                    Otwórz arkusz <ChevronRight className="h-4 w-4" aria-hidden />
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-6 text-center text-muted">
                  Brak arkuszy.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </>
  );
}
