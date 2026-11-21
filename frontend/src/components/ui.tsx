"use client";

import { Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import type { ButtonHTMLAttributes, ComponentProps, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "ai";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover",
  secondary: "bg-white text-foreground border border-border hover:bg-slate-50",
  ghost: "text-foreground hover:bg-slate-100",
  danger: "bg-white text-red-700 border border-red-200 hover:bg-red-50",
  ai: "bg-ai text-white hover:bg-violet-800",
};

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1 text-sm" : "px-4 py-2 text-sm",
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-lg border border-border bg-white shadow-sm", className)} {...props} />;
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Badge({
  tone = "slate",
  className,
  children,
  title,
}: {
  tone?: "slate" | "green" | "red" | "amber" | "blue" | "violet";
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200",
    red: "bg-red-50 text-red-800 ring-1 ring-red-200",
    amber: "bg-amber-50 text-amber-900 ring-1 ring-amber-200",
    blue: "bg-blue-50 text-blue-800 ring-1 ring-blue-200",
    violet: "bg-ai-bg text-ai ring-1 ring-violet-200",
  };
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn("w-full rounded-md border border-border bg-white px-3 py-2 text-sm focus:border-primary focus:outline-none", props.className)}
    />
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-md border border-border bg-white px-3 py-2 text-sm leading-relaxed focus:border-primary focus:outline-none",
        props.className,
      )}
    />
  );
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700">
      {children}
    </label>
  );
}

export function Spinner({ label = "Ładowanie…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

export function AiLabel({ model }: { model?: string }) {
  return (
    <Badge tone="violet" title="Treść wygenerowana przez AI - wymaga decyzji człowieka (AI Act)">
      <Sparkles className="h-3 w-3" aria-hidden /> Propozycja AI{model ? ` · ${model}` : ""}
    </Badge>
  );
}

export function PageTitle({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Sentiment({ value }: { value: string | null }) {
  if (value === "positive") return <Badge tone="green">pozytywna</Badge>;
  if (value === "negative") return <Badge tone="red">do poprawy</Badge>;
  if (value === "neutral") return <Badge>neutralna</Badge>;
  return <Badge tone="amber">analiza AI…</Badge>;
}

/** Licznik czasu przy wywołaniach modelu - lokalny model na zwykłym sprzęcie odpowiada kilkadziesiąt sekund. */
export function AiWaiting({ active, typical = "30–60 s" }: { active: boolean; typical?: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const start = Date.now();
    const t = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => {
      clearInterval(t);
      setSeconds(0);
    };
  }, [active]);
  if (!active) return null;
  return (
    <p className="flex items-center gap-1.5 text-xs text-ai" role="status" aria-live="polite">
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
      Model lokalny przygotowuje odpowiedź… {seconds} s (zwykle {typical}). Dane nie opuszczają serwera.
    </p>
  );
}
