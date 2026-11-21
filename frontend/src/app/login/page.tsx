"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BarChart3, FileCheck2, NotebookPen, ShieldCheck, UserCog, UserRound, Users } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { homeFor } from "@/components/app-shell";
import { BrandMark, BrandName, BrandWave } from "@/components/brand";
import { Button, Card, ErrorBox, Input, Label } from "@/components/ui";
import { api, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";
import { cn } from "@/lib/utils";

// Konta demonstracyjne (hasło demo123) - każde pokazuje inną część systemu.
// Każdy pracownik w danych demo ma własne konto w formacie imie.nazwisko@demo.gov.pl.
const DEMO = [
  {
    email: "marek.zielinski@demo.gov.pl",
    icon: Users,
    label: "Przełożony",
    who: "Marek Zieliński · Wydział Cyfryzacji",
    hint: "zespół na różnych etapach oceny, przypomnienia, asystent AI, HR partner, IPR",
  },
  {
    email: "anna.kowalska@demo.gov.pl",
    icon: UserRound,
    label: "Pracownik",
    who: "Anna Kowalska",
    hint: "samoocena, potwierdzenia, zapoznanie z oceną, sprzeciw, wniosek o zmianę terminu",
  },
  {
    email: "hr@demo.gov.pl",
    icon: BarChart3,
    label: "HR / Dyrektor generalny",
    who: "Iwona Malinowska",
    hint: "Kadry: pracownicy, zastępstwa, import, zestawienia; sprzeciwy, zatwierdzanie IPR, dashboard",
  },
  {
    email: "admin@demo.gov.pl",
    icon: UserCog,
    label: "Administrator",
    who: "Administrator systemu",
    hint: "konta użytkowników i tryb korekty błędów w arkuszach (z powodem i historią); bez wglądu w dziennik i szkice ocen",
  },
  {
    email: "piotr.nowak@demo.gov.pl",
    icon: UserRound,
    label: "Pracownik (kolejne konto)",
    who: "Piotr Nowak",
    hint: "każdy pracownik ma własne konto służbowe; tu ocena z „zapomnianymi” obserwacjami",
  },
  {
    email: "ewa.dabrowska@demo.gov.pl",
    icon: Users,
    label: "Przełożona (zastępstwo)",
    who: "Ewa Dąbrowska · Obsługa Klienta",
    hint: "„łagodna” oceniająca na dashboardzie; po wprowadzeniu zastępstwa przejmuje zespół Marka",
  },
  {
    email: "andrzej.krawczyk@demo.gov.pl",
    icon: Users,
    label: "Przełożony (surowy)",
    who: "Andrzej Krawczyk · Finanse",
    hint: "„surowy” oceniający w kalibracji; wydział z ocenami negatywnymi",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [email, setEmail] = useState("marek.zielinski@demo.gov.pl");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  async function login(e?: FormEvent, asEmail?: string) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api<{ access_token: string; user: Me }>("/auth/login", {
        method: "POST",
        json: { email: asEmail ?? email, password: asEmail ? "demo123" : password },
      });
      setToken(res.access_token);
      qc.clear();
      router.replace(homeFor(res.user.role));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  const tile = (d: (typeof DEMO)[number], big: boolean) => {
    const Icon = d.icon;
    return (
      <button
        key={d.email}
        type="button"
        disabled={loading}
        onClick={() => {
          setEmail(d.email);
          login(undefined, d.email);
        }}
        className={cn(
          "group w-full rounded-lg border border-border bg-white text-left transition hover:border-primary hover:shadow-md disabled:opacity-60",
          big ? "p-4" : "px-3 py-2",
        )}
      >
        <span className="flex items-center gap-2">
          <Icon className={cn("shrink-0 text-primary", big ? "h-5 w-5" : "h-4 w-4")} aria-hidden />
          <span className={cn("font-semibold", big ? "font-serif text-base" : "text-sm")}>{d.label}</span>
          <ArrowRight className="ml-auto h-4 w-4 text-muted opacity-0 transition group-hover:opacity-100" aria-hidden />
        </span>
        <span className="mt-0.5 block text-xs text-muted">{d.who}</span>
        {big && <span className="mt-1.5 block text-xs leading-snug text-slate-600">{d.hint}</span>}
      </button>
    );
  };

  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      {/* panel identyfikacji: barwy instytucji, hasło projektu */}
      <section className="relative overflow-hidden bg-primary px-6 py-8 text-white sm:px-10 lg:py-14">
        <div className="flex items-center gap-3">
          <BrandMark className="h-11 w-11 ring-1 ring-white/30 rounded-[7px]" />
          <BrandName inverted />
        </div>
        <h1 className="mt-10 max-w-md font-serif text-3xl font-semibold leading-tight sm:text-4xl lg:mt-20">
          AI sugeruje,
          <br />
          człowiek decyduje.
        </h1>
        <p className="mt-4 max-w-md text-sm leading-relaxed text-white/80">
          Ocena okresowa, która wspiera rozwój pracownika, zamiast być kolejnym formularzem do wypełnienia. Zgodna
          z ustawą o służbie cywilnej i rozporządzeniem w sprawie ocen okresowych.
        </p>
        <ul className="mt-8 hidden max-w-md space-y-3 text-sm sm:block">
          {[
            [NotebookPen, "Dziennik obserwacji przez cały 24-miesięczny okres oceny"],
            [FileCheck2, "Każde zdanie uzasadnienia wskazuje notatkę źródłową"],
            [ShieldCheck, "Model językowy działa lokalnie - dane nie opuszczają urzędu"],
          ].map(([Icon, text]) => {
            const I = Icon as typeof ShieldCheck;
            return (
              <li key={text as string} className="flex items-start gap-3">
                <I className="mt-0.5 h-4 w-4 shrink-0 text-white/70" aria-hidden />
                <span className="text-white/90">{text as string}</span>
              </li>
            );
          })}
        </ul>
        <BrandWave className="pointer-events-none absolute -bottom-2 left-0 h-24 w-full opacity-90" />
      </section>

      {/* wybór roli */}
      <section className="flex items-center justify-center px-4 py-8 sm:px-8">
        <div className="w-full max-w-2xl">
          <h2 className="font-serif text-2xl font-semibold">Wejdź do systemu</h2>
          <p className="mt-1 text-sm text-muted">Konta demonstracyjne - jedno kliknięcie, hasło: demo123. Wszystkie dane są fikcyjne.</p>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">{DEMO.slice(0, 4).map((d) => tile(d, true))}</div>

          <details className="mt-4 rounded-lg border border-border bg-white/60">
            <summary className="cursor-pointer px-4 py-2.5 text-sm font-medium text-slate-700">Więcej kont demo ({DEMO.length - 4})</summary>
            <div className="grid gap-2 px-4 pb-4 sm:grid-cols-3">{DEMO.slice(4).map((d) => tile(d, false))}</div>
          </details>

          <Card className="mt-4 p-5">
            <form onSubmit={login} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <div>
                <Label htmlFor="email">E-mail służbowy</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
              </div>
              <div>
                <Label htmlFor="password">Hasło</Label>
                <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
              </div>
              <Button type="submit" loading={loading}>
                Zaloguj
              </Button>
            </form>
            <div className="mt-3">
              <ErrorBox error={error} />
            </div>
          </Card>
        </div>
      </section>
    </main>
  );
}
