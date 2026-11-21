"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, PenLine } from "lucide-react";
import Link from "next/link";
import { useMe } from "@/components/app-shell";
import { NoteComposer, NotesList } from "@/components/notes";
import { Reminders } from "@/components/reminders";
import { Badge, Button, Card, CardHeader, ErrorBox, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { EmployeeDetail } from "@/lib/types";
import { STATUS_LABEL, statusTone } from "@/lib/utils";

export default function MyPage() {
  const me = useMe();
  const empId = me?.employee_id;
  const { data: emp, error, isPending } = useQuery({
    queryKey: ["employee", empId],
    queryFn: () => api<EmployeeDetail>(`/employees/${empId}`),
    enabled: !!empId,
  });
  if (!empId) return <p className="text-sm text-muted">To konto nie jest powiązane z pracownikiem.</p>;
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  return (
    <>
      <PageTitle title={`Dzień dobry, ${emp.full_name.split(" ")[0]}`} subtitle={`${emp.position} · przełożony: ${emp.manager_name ?? "-"}`} />
      <Reminders title="Do zrobienia" scope="self" />
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="mb-1 text-base font-semibold">Moje osiągnięcia</h2>
            <p className="mb-3 text-sm text-muted">Zapisuj sukcesy na bieżąco - przełożony zobaczy je w dzienniku, a Ty łatwiej wypełnisz samoocenę.</p>
            <NoteComposer employeeId={emp.id} placeholder="Np. „Ukończyłam kurs X”, „Przygotowałam prezentację dla 100 osób”…" />
          </Card>
          <NotesList employeeId={emp.id} canEdit={false} myUserId={me?.id} />
        </div>
        <Card>
          <CardHeader title="Moje oceny okresowe" subtitle="Twoje wpisy w dzienniku widzi przełożony. Notatki przełożonego zobaczysz, gdy zdecyduje się je udostępnić." />
          <ul className="divide-y divide-border">
            {emp.reviews.length === 0 && <li className="px-5 py-3 text-sm text-muted">Brak ocen.</li>}
            {emp.reviews.map((r) => (
              <li key={r.id} className="space-y-2 px-5 py-4 text-sm">
                <div className="flex items-center justify-between">
                  <Link href={`/reviews/${r.id}`} className="flex items-center gap-2 font-medium text-primary hover:underline">
                    <FileText className="h-4 w-4" aria-hidden /> {r.cycle_name}
                  </Link>
                  <Badge tone={statusTone(r.status)}>{STATUS_LABEL[r.status]}</Badge>
                </div>
                {r.overall_level && <p className="text-muted">Poziom: {r.overall_level}</p>}
                {["observation", "draft"].includes(r.status) && (
                  <Link href={`/reviews/${r.id}/self`}>
                    <Button size="sm" variant="secondary">
                      <PenLine className="h-4 w-4" aria-hidden /> Samoocena
                    </Button>
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
