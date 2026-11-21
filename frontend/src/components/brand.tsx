import { cn } from "@/lib/utils";

/** Własny znak aplikacji (nie logo Służby Cywilnej - to zawiera godło i wymaga zgody KPRM):
 *  arkusz oceny w barwach instytucji, z czerwoną kreską podpisu jak na okładce poradnika KPRM. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={cn("h-9 w-9 shrink-0", className)} role="img" aria-label="Cyfrowy Asystent Ocen Okresowych">
      <rect width="40" height="40" rx="7" fill="var(--primary)" />
      <path d="M12 8h12l6 6v16a2 2 0 0 1-2 2H12a2 2 0 0 1-2-2V10a2 2 0 0 1 2-2Z" fill="#fff" />
      <path d="M24 8v6h6" fill="none" stroke="var(--primary)" strokeOpacity=".35" strokeWidth="1.2" />
      <path d="M14 15h7M14 19h12M14 23h9" stroke="var(--primary)" strokeOpacity=".55" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M5 33c5-3.5 9 2 14-1.2s8-4.8 16-2.3" fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/** Czerwona fala - motyw z okładki poradnika „Oceny okresowe w służbie cywilnej” (KPRM). */
export function BrandWave({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 60" preserveAspectRatio="none" className={className} aria-hidden>
      <path
        d="M0 44c40-6 70-14 96-8s30 16 58 10 36-30 70-34 50 22 84 20 52-16 92-18"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function BrandName({ inverted }: { inverted?: boolean }) {
  return (
    <span className="leading-tight">
      <span className={cn("block font-serif text-[17px] font-semibold", inverted ? "text-white" : "text-primary")}>Asystent Ocen Okresowych</span>
      <span className={cn("block text-[11px] uppercase tracking-[0.12em]", inverted ? "text-white/70" : "text-muted")}>
        Służba cywilna
      </span>
    </span>
  );
}
