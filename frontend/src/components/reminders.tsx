"use client";

import { useQuery } from "@tanstack/react-query";
import { BellRing, ChevronRight } from "lucide-react";
import Link from "next/link";
import { Card, CardHeader } from "@/components/ui";
import { api } from "@/lib/api";
import type { Reminder } from "@/lib/types";
import { cn, daysTo, fmtDate } from "@/lib/utils";

const TONE: Record<Reminder["severity"], string> = {
  critical: "border-l-red-600 bg-red-50/60",
  warning: "border-l-amber-500 bg-amber-50/60",
  info: "border-l-slate-300",
};

function dueText(due: string | null) {
  const d = daysTo(due);
  if (d === null) return null;
  if (d < 0) return `po terminie (${fmtDate(due)})`;
  if (d === 0) return "termin dziś";
  return `do ${fmtDate(due)} · ${d} dni`;
}

export function Reminders({ title = "Terminy i przypomnienia", limit = 8 }: { title?: string; limit?: number }) {
  const { data } = useQuery({ queryKey: ["reminders"], queryFn: () => api<Reminder[]>("/reminders") });
  if (!data || data.length === 0) return null;
  return (
    <Card className="mb-6">
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <BellRing className="h-4 w-4 text-primary" aria-hidden /> {title}
          </span>
        }
        subtitle="Terminy liczone wg ustawy o służbie cywilnej (art. 81, 83, 89) z uwzględnieniem dni wolnych i nieobecności."
      />
      <ul className="divide-y divide-border">
        {data.slice(0, limit).map((r, i) => (
          <li key={`${r.kind}-${i}`} className={cn("border-l-4", TONE[r.severity])}>
            <Link href={r.link} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{r.title}</div>
                <div className="text-xs text-muted">{r.detail}</div>
              </div>
              {r.due && (
                <span className={cn("shrink-0 text-xs", r.severity === "critical" ? "font-semibold text-red-700" : "text-slate-600")}>
                  {dueText(r.due)}
                </span>
              )}
              <ChevronRight className="h-4 w-4 shrink-0 text-muted" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
