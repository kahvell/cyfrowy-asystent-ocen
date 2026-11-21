import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleDateString("pl-PL", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export const STATUS_LABEL: Record<string, string> = {
  criteria: "Wyznaczanie kryteriów",
  observation: "Okres oceny",
  draft: "Przygotowanie oceny",
  submitted: "Gotowa do rozmowy",
  discussed: "Po rozmowie oceniającej",
  final: "Przekazana do zapoznania",
  acknowledged: "Zakończona",
  objection: "Sprzeciw",
};

export const DONE_STATUSES = ["final", "acknowledged", "objection"];

export function statusTone(s: string): "green" | "blue" | "amber" | "red" | "slate" {
  if (s === "acknowledged") return "green";
  if (s === "objection") return "red";
  if (s === "final") return "amber";
  if (s === "criteria" || s === "observation") return "slate";
  return "blue";
}

/** dni do terminu (ujemne = po terminie) */
export function daysTo(iso: string | null | undefined) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  const t = new Date();
  t.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - t.getTime()) / 86400000);
}

export const SCALE: { value: number; label: string; short: string }[] = [
  { value: 1, label: "znacznie poniżej oczekiwań", short: "zn. poniżej" },
  { value: 3, label: "poniżej oczekiwań", short: "poniżej" },
  { value: 5, label: "na poziomie oczekiwań", short: "na poziomie" },
  { value: 7, label: "powyżej oczekiwań", short: "powyżej" },
  { value: 9, label: "znacznie powyżej oczekiwań", short: "zn. powyżej" },
];

export function scaleLabel(v: number | null | undefined) {
  return SCALE.find((s) => s.value === v)?.label ?? "brak oceny";
}

export function modelLabel(model: string) {
  if (model.startsWith("heuristic")) return model.includes("fallback") ? "reguły (model niedostępny)" : "reguły / heurystyki";
  if (model === "rules") return "reguły";
  if (model === "none") return "-";
  return model.replace(/^ollama(_chat)?\//, "");
}
