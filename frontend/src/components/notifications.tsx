"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Mail } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Notice {
  id: number;
  subject: string;
  body: string;
  link: string;
  created_at: string;
  read: boolean;
  emailed: boolean;
}

export function NotificationsBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data = [] } = useQuery({ queryKey: ["notifications"], queryFn: () => api<Notice[]>("/notifications"), refetchInterval: 30000 });
  const unread = data.filter((n) => !n.read).length;
  const markRead = useMutation({
    mutationFn: () => api("/notifications/read", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && unread) markRead.mutate();
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={toggle} className="relative rounded-md p-2 text-slate-600 hover:bg-slate-100" aria-label={`Powiadomienia (${unread} nowych)`} aria-expanded={open}>
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-600 px-1.5 text-[10px] font-semibold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-[min(92vw,380px)] rounded-lg border border-border bg-white shadow-lg">
          <div className="border-b border-border px-4 py-2 text-sm font-semibold">Powiadomienia</div>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto">
            {data.length === 0 && <li className="px-4 py-3 text-sm text-muted">Brak powiadomień.</li>}
            {data.map((n) => (
              <li key={n.id} className={cn("px-4 py-2.5 text-sm", !n.read && "bg-blue-50/60")}>
                <Link href={n.link || "/"} onClick={() => setOpen(false)} className="block hover:underline">
                  <div className="font-medium">{n.subject}</div>
                  {n.body && <div className="line-clamp-2 text-xs text-slate-600">{n.body}</div>}
                </Link>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted">
                  {new Date(n.created_at + "Z").toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" })}
                  {n.emailed && (
                    <span className="inline-flex items-center gap-0.5">
                      <Mail className="h-3 w-3" aria-hidden /> wysłano e-mail
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
