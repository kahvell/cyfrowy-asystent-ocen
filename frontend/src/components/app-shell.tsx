"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, BookOpen, ClipboardList, IdCard, LogOut, ShieldCheck, TrendingUp, Users, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, use, useContext, useEffect, type ReactNode } from "react";
import { browser } from "react-dom";
import { api, getToken, setToken } from "@/lib/api";
import type { Me, SystemInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { NotificationsBell } from "./notifications";
import { Spinner } from "./ui";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext);

const NAV: { href: string; label: string; roles: string[]; icon: typeof Users }[] = [
  { href: "/team", label: "Mój zespół", roles: ["manager"], icon: Users },
  { href: "/team", label: "Wszyscy pracownicy", roles: ["admin"], icon: Users },
  { href: "/stats", label: "Statystyki ocen", roles: ["manager", "admin"], icon: TrendingUp },
  { href: "/me", label: "Moja ocena i rozwój", roles: ["employee", "manager"], icon: UserRound },
  { href: "/dashboard", label: "Dashboard urzędu", roles: ["hr"], icon: BarChart3 },
  { href: "/hr", label: "Kadry", roles: ["hr", "admin"], icon: IdCard },
  { href: "/assistant", label: "Asystent przepisów", roles: ["employee", "manager", "hr", "admin"], icon: BookOpen },
];

export function homeFor(role: string) {
  if (role === "hr") return "/dashboard";
  if (role === "employee") return "/me";
  return "/team";
}

function ModelBanner() {
  const { data } = useQuery({ queryKey: ["system"], queryFn: () => api<SystemInfo>("/system/info"), staleTime: 60_000 });
  if (!data) return null;
  const local = !data.data_leaves_server;
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-1.5 text-xs",
        local ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900",
      )}
      title={data.legal_basis}
    >
      <ShieldCheck className="h-4 w-4 shrink-0" aria-hidden />
      <span>
        {data.llm_mode === "fake"
          ? "Tryb offline: reguły bez modelu językowego"
          : local
            ? `Model lokalny: ${data.llm_model.replace(/^ollama(_chat)?\//, "")} · dane nie opuszczają serwera urzędu`
            : `Zewnętrzne API (${data.llm_model}) · dane pseudonimizowane`}
      </span>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  // Token żyje w localStorage, więc powłoka renderuje się tylko w przeglądarce.
  use(browser("Sesja użytkownika jest przechowywana w localStorage."));
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const isLogin = pathname === "/login";
  const token = getToken();

  const { data: me, isPending } = useQuery({
    queryKey: ["me", token],
    queryFn: () => api<Me>("/me"),
    enabled: !!token && !isLogin,
  });

  useEffect(() => {
    if (!token && !isLogin) router.replace("/login");
  }, [token, isLogin, router]);

  if (isLogin) return <>{children}</>;
  if (!token || isPending || !me) return <Spinner />;

  const logout = () => {
    setToken(null);
    qc.clear();
    router.replace("/login");
  };

  return (
    <MeContext.Provider value={me}>
      <div className="flex min-h-screen flex-col">
        <header className="border-b border-border bg-white print:hidden">
          <div className="h-1 bg-gradient-to-r from-white via-white to-accent" aria-hidden />
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href={homeFor(me.role)} className="flex items-center gap-2">
              <ClipboardList className="h-6 w-6 text-primary" aria-hidden />
              <span className="font-semibold leading-tight">
                Cyfrowy Asystent
                <br className="hidden sm:block" />
                <span className="text-sm font-normal text-muted"> Ocen Okresowych</span>
              </span>
            </Link>
            <nav className="flex flex-wrap gap-1" aria-label="Główna nawigacja">
              {NAV.filter((n) => n.roles.includes(me.role)).map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm",
                    pathname.startsWith(href) ? "bg-primary/10 font-medium text-primary" : "text-slate-700 hover:bg-slate-100",
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden /> {label}
                </Link>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-3">
              <ModelBanner />
              <div className="text-right text-sm">
                <div className="font-medium">{me.full_name}</div>
                <div className="text-xs text-muted">{me.position ?? { hr: "HR", admin: "Administrator" }[me.role as "hr"]}</div>
              </div>
              <NotificationsBell />
              <button onClick={logout} className="rounded-md p-2 text-slate-600 hover:bg-slate-100" aria-label="Wyloguj">
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 print:max-w-none print:p-0">{children}</main>
        <footer className="border-t border-border bg-white py-3 text-center text-xs text-muted print:hidden">
          AI sugeruje, człowiek decyduje · ocena wg rozporządzenia PRM z 4.04.2016 r. (Dz.U. 2016 poz. 470) · dane demonstracyjne
        </footer>
      </div>
    </MeContext.Provider>
  );
}
