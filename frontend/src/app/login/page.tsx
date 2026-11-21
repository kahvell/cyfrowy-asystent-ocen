"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { homeFor } from "@/components/app-shell";
import { Button, Card, ErrorBox, Input, Label } from "@/components/ui";
import { api, setToken } from "@/lib/api";
import type { Me } from "@/lib/types";

const DEMO = [
  { email: "kierownik@demo.gov.pl", label: "Przełożony", who: "Marek Zieliński, Wydział Cyfryzacji" },
  { email: "pracownik@demo.gov.pl", label: "Pracownik", who: "Anna Kowalska" },
  { email: "hr@demo.gov.pl", label: "HR / Dyrektor generalny", who: "dashboard urzędu" },
];

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [email, setEmail] = useState("kierownik@demo.gov.pl");
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
        json: { email: asEmail ?? email, password },
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

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <ClipboardList className="h-9 w-9 text-primary" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold">Cyfrowy Asystent Ocen Okresowych</h1>
            <p className="text-sm text-muted">Służba cywilna · AI sugeruje, człowiek decyduje</p>
          </div>
        </div>
        <Card className="p-6">
          <form onSubmit={login} className="space-y-4">
            <div>
              <Label htmlFor="email">E-mail służbowy</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
            </div>
            <div>
              <Label htmlFor="password">Hasło</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </div>
            <ErrorBox error={error} />
            <Button type="submit" loading={loading} className="w-full">
              Zaloguj
            </Button>
          </form>
          <div className="mt-6 border-t border-border pt-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Konta demo (hasło: demo123)</p>
            <div className="space-y-2">
              {DEMO.map((d) => (
                <button
                  key={d.email}
                  type="button"
                  onClick={() => {
                    setEmail(d.email);
                    login(undefined, d.email);
                  }}
                  className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-slate-50"
                >
                  <span className="font-medium">{d.label}</span>
                  <span className="text-xs text-muted">{d.who}</span>
                </button>
              ))}
            </div>
          </div>
        </Card>
        <p className="mt-4 text-center text-xs text-muted">Wszystkie dane w systemie demo są fikcyjne.</p>
      </div>
    </main>
  );
}
