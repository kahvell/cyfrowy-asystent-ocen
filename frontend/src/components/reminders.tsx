"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BellRing, CalendarClock, ChevronRight } from "lucide-react";
import Link from "next/link";
import { Card, CardHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Reminder } from "@/lib/types";
import { cn, daysTo, fmtDate } from "@/lib/utils";

const TONE: Record<Reminder["severity"], string> = {
  critical: "border-l-red-600 bg-red-50/70",
  warning: "border-l-amber-500 bg-amber-50/50",
  info: "border-l-slate-300",
};

const DUE_TONE: Record<Reminder["severity"], string> = {
  critical: "bg-red-100 text-red-800",
  warning: "bg-amber-100 text-amber-900",
  info: "bg-slate-100 text-slate-700",
};

function dueText(due: string) {
  const d = daysTo(due);
  if (d === null) return fmtDate(due);
  if (d < 0) return `termin minął ${fmtDate(due)} (${-d} dni temu)`;
  if (d === 0) return `termin: dziś (${fmtDate(due)})`;
  if (d === 1) return `termin: jutro (${fmtDate(due)})`;
  return `termin: ${fmtDate(due)} · zostało ${d} dni`;
}

export function Reminders({ title = "Terminy i przypomnienia", limit = 8 }: { title?: string; limit?: number }) {
  const { data } = useQuery({ queryKey: ["reminders"], queryFn: () => api<Reminder[]>("/reminders") });
  if (!data || data.length === 0) return null;
  const urgent = data.filter((r) => r.severity !== "info").length;
  return (
    <Card className="mb-6">
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <BellRing className="h-4 w-4 text-primary" aria-hidden /> {title}
            {urgent > 0 && <span className="rounded-full bg-amber-500 px-2 py-0.5 text-xs font-semibold text-white">{urgent} pilne</span>}
          </span>
        }
        subtitle="Terminy liczone wg ustawy o służbie cywilnej i rozporządzenia, z uwzględnieniem dni wolnych od pracy i nieobecności."
      />
      <ul className="divide-y divide-border">
        {data.slice(0, limit).map((r, i) => (
          <li key={`${r.kind}-${i}`} className={cn("border-l-4", TONE[r.severity])}>
            <Link href={r.link} className="group flex flex-col gap-2 px-5 py-3 hover:bg-white/60 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-sm font-medium">
                  {r.severity === "critical" && <AlertTriangle className="h-4 w-4 shrink-0 text-red-700" aria-hidden />}
                  {r.title}
                </div>
                <div className="mt-0.5 text-xs text-slate-600">{r.detail}</div>
                {r.due && (
                  <span className={cn("mt-1.5 inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium", DUE_TONE[r.severity])}>
                    <CalendarClock className="h-3.5 w-3.5" aria-hidden /> {dueText(r.due)}
                  </span>
                )}
              </div>
              <span className="inline-flex shrink-0 items-center gap-1 self-start rounded-md border border-border bg-white px-3 py-1.5 text-xs font-medium text-primary group-hover:border-primary sm:self-center">
                Otwórz <ChevronRight className="h-3.5 w-3.5" aria-hidden />
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {data.length > limit && <p className="px-5 py-2 text-xs text-muted">… i {data.length - limit} kolejnych.</p>}
    </Card>
  );
}
