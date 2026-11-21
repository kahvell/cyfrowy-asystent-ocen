"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Play } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMe } from "@/components/app-shell";
import { HrPartnerPanel } from "@/components/hr-partner";
import { NoteComposer, NotesList } from "@/components/notes";
import { Badge, Button, Card, CardHeader, ErrorBox, PageTitle, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Cycle, EmployeeDetail, Review } from "@/lib/types";
import { STATUS_LABEL, statusTone } from "@/lib/utils";

const SHEET_INFO: Record<string, string> = {
  A: "arkusz A - kierownik urzędu",
  B: "arkusz B - stanowisko polegające na bezpośrednim kierowaniu pracownikami",
  C: "arkusz C - pozostałe stanowiska",
};

function StartReview({ emp }: { emp: EmployeeDetail }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: cycles } = useQuery({ queryKey: ["cycles"], queryFn: () => api<Cycle[]>("/cycles") });
  const open = cycles?.find((c) => c.status === "open");
  const create = useMutation({
    mutationFn: () => api<Review>("/reviews", { method: "POST", json: { employee_id: emp.id, cycle_id: open!.id, additional_criterion_ids: [] } }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["team"] });
      qc.invalidateQueries({ queryKey: ["reminders"] });
      router.push(`/reviews/${r.id}`);
    },
  });
  if (!open || emp.reviews.some((r) => r.cycle_id === open.id)) return null;
  if (emp.contract_type === "okreslony")
    return (
      <Card className="p-5 text-sm">
        <h2 className="mb-1 font-semibold">Nie podlega ocenie okresowej</h2>
        <p className="text-slate-600">
          Ocenie okresowej podlegają urzędnicy służby cywilnej i pracownicy zatrudnieni na czas nieokreślony (art. 81 ust. 1 ustawy). Osoba na umowie na czas
          określony podlega pierwszej ocenie w służbie cywilnej (art. 37-38) - odrębny tryb, poza zakresem systemu.
        </p>
      </Card>
    );
  return (
    <Card>
      <CardHeader title="Rozpocznij cykl oceny okresowej" subtitle={`Dobrany automatycznie wg stanowiska: ${SHEET_INFO[emp.sheet_type] ?? emp.sheet_type}`} />
      <div className="space-y-3 p-5 text-sm">
        <p className="text-slate-600">
          System wyliczy termin wyznaczenia kryteriów (30 dni, a po ocenie negatywnej 7 dni) i termin sporządzenia oceny (24 miesiące, z uwzględnieniem
          nieobecności). Kryteria dodatkowe wybierzesz w części I arkusza.
        </p>
        {emp.senior_position && (
          <p className="rounded-md border border-amber-300 bg-amber-50 p-2 text-amber-900">
            Wyższe stanowisko w służbie cywilnej (art. 52): wg poradnika KPRM (rozdz. 3) nie podlega ocenie okresowej z art. 81, dlatego cykl nie startuje
            automatycznie. Możesz założyć ocenę ręcznie, zgodnie z praktyką urzędu. IPR nie jest wtedy sporządzany (art. 108).
          </p>
        )}
        <ErrorBox error={create.error} />
        <Button onClick={() => create.mutate()} loading={create.isPending}>
          <Play className="h-4 w-4" aria-hidden /> Utwórz arkusz {emp.sheet_type}
        </Button>
      </div>
    </Card>
  );
}

export default function EmployeePage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const empId = Number(id);
  const { data: emp, error, isPending } = useQuery({ queryKey: ["employee", empId], queryFn: () => api<EmployeeDetail>(`/employees/${empId}`) });

  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;
  const isManager = me?.role === "manager" || me?.role === "admin";

  return (
    <>
      <PageTitle
        title={emp.full_name}
        subtitle={`${emp.position} · ${emp.department ?? ""} · ${emp.is_civil_servant ? "urzędnik służby cywilnej" : "pracownik służby cywilnej"}`}
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {isManager && (
            <Card className="p-5">
              <h2 className="mb-3 text-base font-semibold">Dodaj obserwację</h2>
              <NoteComposer employeeId={empId} managerView />
            </Card>
          )}
          <NotesList employeeId={empId} canEdit={isManager} canShare={isManager} myUserId={me?.id} />
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Oceny okresowe" />
            <ul className="divide-y divide-border">
              {emp.reviews.length === 0 && <li className="px-5 py-3 text-sm text-muted">Brak ocen.</li>}
              {emp.reviews.map((r) => (
                <li key={r.id} className="flex items-center justify-between px-5 py-3 text-sm">
                  <Link href={`/reviews/${r.id}`} className="flex items-center gap-2 font-medium text-primary hover:underline">
                    <FileText className="h-4 w-4" aria-hidden /> {r.cycle_name}
                  </Link>
                  <Badge tone={statusTone(r.status)}>{STATUS_LABEL[r.status]}</Badge>
                </li>
              ))}
            </ul>
          </Card>
          {isManager && <StartReview emp={emp} />}
          {me?.role === "manager" && (
            <HrPartnerPanel
              employeeId={empId}
              onShowNote={(nid) => document.getElementById(`note-${nid}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
            />
          )}
          <Card className="p-5 text-sm">
            <h2 className="mb-2 font-semibold">Opis stanowiska</h2>
            <p className="text-muted">{emp.position_description || "brak"}</p>
          </Card>
        </div>
      </div>
    </>
  );
}
