"use client";

import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { Button, ErrorBox, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { Review } from "@/lib/types";
import FOOTNOTES from "@/lib/form-footnotes.json";
import { fmtDate, SCALE } from "@/lib/utils";

// Wzory arkuszy: załączniki nr 2-4 do rozporządzenia PRM z 4.04.2016 r. (Dz.U. poz. 470)
const ANNEX: Record<string, string> = { A: "2", B: "3", C: "4" };
const LEVELS = [
  ["od 1 punktu do 2 punktów", "znacznie poniżej oczekiwań"],
  ["powyżej 2 punktów do 4 punktów", "poniżej oczekiwań"],
  ["powyżej 4 punktów do 6 punktów", "na poziomie oczekiwań"],
  ["powyżej 6 punktów do 8 punktów", "powyżej oczekiwań"],
  ["powyżej 8 punktów do 9 punktów", "znacznie powyżej oczekiwań"],
];

// Numeracja objaśnień we wzorach arkuszy (załączniki nr 2-4 do rozporządzenia); arkusz A ma ich 16, B i C - 18.
type FnKey = "title" | "position" | "extra1" | "topics" | "conv" | "from" | "to" | "partial" | "extra2" | "pos" | "neg" | "just" | "ipr" | "prevResult" | "prevLevel" | "request" | "objection" | "part3";
const FN_BC: Record<FnKey, number> = { title: 1, position: 2, extra1: 3, topics: 4, conv: 5, from: 6, to: 7, partial: 8, extra2: 9, pos: 10, neg: 11, just: 12, ipr: 13, prevResult: 14, prevLevel: 15, request: 16, objection: 17, part3: 18 };
const FN_A: Partial<Record<FnKey, number>> = { title: 1, extra1: 2, topics: 3, conv: 4, from: 5, to: 6, partial: 7, extra2: 8, pos: 9, neg: 10, just: 11, ipr: 12, prevResult: 13, prevLevel: 14, request: 15, part3: 16 };
const fnNum = (sheet: string, k: FnKey) => (sheet === "A" ? FN_A[k] : FN_BC[k]);

function Fn({ sheet, k }: { sheet: string; k: FnKey }) {
  const n = fnNum(sheet, k);
  return n ? <sup className="text-[9px]">{n})</sup> : null;
}

function Footnotes({ sheet, keys }: { sheet: string; keys: FnKey[] }) {
  const all = (FOOTNOTES as Record<string, Record<string, string>>)[sheet] ?? {};
  const nums = keys.map((k) => fnNum(sheet, k)).filter((n): n is number => !!n);
  if (!nums.length) return null;
  return (
    <ol className="mt-3 list-none space-y-0.5 border-t border-black pt-1 text-[9px] leading-tight text-slate-800">
      {nums.map((n) => (
        <li key={n}>
          <sup>{n})</sup> {all[String(n)]}
        </li>
      ))}
    </ol>
  );
}

const X = ({ on }: { on: boolean }) => <span className="font-bold">{on ? "X" : ""}</span>;

function Cell({ children, className = "", head, colSpan }: { children?: ReactNode; className?: string; head?: boolean; colSpan?: number }) {
  const Tag = head ? "th" : "td";
  return (
    <Tag colSpan={colSpan} className={`border border-black px-2 py-1 text-left align-top ${head ? "bg-slate-100 font-semibold" : ""} ${className}`}>
      {children}
    </Tag>
  );
}

const SIGNATURE: Record<string, string> = {
  system: "<potwierdzono w systemie>",
  elektroniczny: "/podpis elektroniczny/",
  wydruk: "",
};

function Sign({
  place,
  date,
  label,
  name,
  nameLabel = "imię i nazwisko lub pieczątka ocenianego",
  method = "system",
}: {
  place: string;
  date: string | null;
  label: string;
  name?: string;
  nameLabel?: string;
  method?: string;
}) {
  return (
    <table className="mt-2 w-full border-collapse text-[11px]">
      <tbody>
        <tr className="h-8">
          <Cell className="w-1/4">{date ? place : ""}</Cell>
          <Cell className="w-1/4">{date ? fmtDate(date) : ""}</Cell>
          {name !== undefined && <Cell className="w-1/4">{date ? name : ""}</Cell>}
          <Cell>{date ? SIGNATURE[method] ?? "" : ""}</Cell>
        </tr>
        <tr className="text-[10px] text-slate-600">
          <td className="px-2">miejscowość</td>
          <td className="px-2">data (dd.mm.rrrr)</td>
          {name !== undefined && <td className="px-2">{nameLabel}</td>}
          <td className="px-2">{label}</td>
        </tr>
      </tbody>
    </table>
  );
}

// Wzór arkusza A (kierownik urzędu) nie ma pola „Komórka organizacyjna” w danych ocenianego i oceniającego.
function People({ title, p, sheet, positionFn }: { title: string; p: Review["employee_form"]; sheet: string; positionFn?: boolean }) {
  return (
    <>
      <tr>
        <Cell head className="text-center" >
          {title}
        </Cell>
        <Cell head />
      </tr>
      {(
        [
          ["Imię", p.first_name],
          ["Nazwisko", p.last_name],
          ["Komórka organizacyjna", p.department],
          ["Stanowisko pracy", p.position],
        ] as const
      ).filter(([k]) => !(sheet === "A" && k === "Komórka organizacyjna")).map(([k, v]) => (
        <tr key={k}>
          <Cell className="w-1/3">
            {k}
            {positionFn && k === "Stanowisko pracy" && <Fn sheet={sheet} k="position" />}
          </Cell>
          <Cell>{v}</Cell>
        </tr>
      ))}
    </>
  );
}

export default function PrintReview() {
  const { id } = useParams<{ id: string }>();
  const { data: r, error, isPending } = useQuery({ queryKey: ["review", Number(id)], queryFn: () => api<Review>(`/reviews/${id}`) });
  if (isPending) return <Spinner />;
  if (error) return <ErrorBox error={error} />;

  const mandatory = r.criteria.filter((c) => !c.is_additional);
  const additional = r.criteria.filter((c) => c.is_additional);
  const civil = r.employee.is_civil_servant;
  const s = r.summary;

  return (
    <div className="mx-auto max-w-[210mm] bg-white text-[12px] leading-snug text-black">
      <div className="mb-4 flex items-center justify-between gap-2 print:hidden">
        <Link href={`/reviews/${r.id}`} className="text-sm text-primary hover:underline">
          ← wróć do arkusza
        </Link>
        <div className="flex items-center gap-2 text-xs text-muted">
          W oknie drukowania wybierz „Zapisz jako PDF”, aby wyeksportować arkusz do pliku.
          <Button onClick={() => window.print()}>
            <Printer className="h-4 w-4" aria-hidden /> Drukuj / PDF
          </Button>
        </div>
      </div>

      <div className="space-y-4 border border-slate-300 p-[12mm] print:border-0 print:p-0">
        <div className="text-right text-[11px]">
          Załącznik nr {ANNEX[r.sheet_type] ?? "4"}
          <br />
          WZÓR
        </div>
        <header className="text-center">
          <div className="text-base font-bold">ARKUSZ {r.sheet_type}</div>
          <div className="font-bold">OCENA OKRESOWA</div>
          <div className="font-bold">
            URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ
            <Fn sheet={r.sheet_type} k="title" />
          </div>
          {r.attempt > 1 && <div className="mt-1 text-[11px]">(ocena sporządzona po raz drugi w wyniku uwzględnienia sprzeciwu)</div>}
        </header>

        {/* ------------------------------------------------ CZĘŚĆ I */}
        <section className="break-inside-avoid">
          <h2 className="mb-1 font-bold">CZĘŚĆ I</h2>
          <table className="w-full border-collapse">
            <tbody>
              <tr>
                <Cell head className="w-1/3">
                  NAZWA URZĘDU
                </Cell>
                <Cell>{r.office.name}</Cell>
              </tr>
              <People title="DANE OCENIANEGO" p={r.employee_form} sheet={r.sheet_type} positionFn />
              <People title="DANE OCENIAJĄCEGO" p={r.reviewer_form} sheet={r.sheet_type} />
            </tbody>
          </table>

          <table className="mt-3 w-full border-collapse">
            <tbody>
              <tr>
                <Cell head className="text-center" >
                  KRYTERIA OCENY I TERMIN SPORZĄDZENIA OCENY
                </Cell>
                <Cell head />
              </tr>
              <tr>
                <Cell head>Kryteria obowiązkowe</Cell>
                <Cell head>
                  Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3)
                  <Fn sheet={r.sheet_type} k="extra1" />
                </Cell>
              </tr>
              {Array.from({ length: Math.max(mandatory.length, 3) }).map((_, i) => (
                <tr key={i}>
                  <Cell>{mandatory[i]?.name ?? ""}</Cell>
                  <Cell>{i < 3 ? (additional[i]?.name ?? (i === 0 && additional.length === 0 ? "brak" : "")) : ""}</Cell>
                </tr>
              ))}
              <tr>
                <Cell head>Termin sporządzenia oceny</Cell>
                <Cell>{fmtDate(r.deadlines.due_date)} (dd.mm.rrrr)</Cell>
              </tr>
            </tbody>
          </table>
          <p className="mt-2">Potwierdzamy:</p>
          <ul className="list-disc pl-6">
            <li>
              przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu
              przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470), i omówienie w trakcie tej rozmowy wszystkich
              wymaganych zagadnień
              <Fn sheet={r.sheet_type} k="topics" />,
            </li>
            <li>zapoznanie ocenianego z kryteriami oceny oraz terminem sporządzenia oceny.</li>
          </ul>
          <Sign place={r.criteria_reviewer_place} date={r.criteria_reviewer_confirmed_at} label="podpis oceniającego" method={r.signature_method} />
          <Sign place={r.criteria_employee_place} date={r.criteria_employee_confirmed_at} label="podpis ocenianego" method={r.signature_method} />
          <Footnotes sheet={r.sheet_type} keys={["title", "position", "extra1", "topics"]} />
        </section>

        {/* ------------------------------------------------ CZĘŚĆ II */}
        <section className="break-before-page">
          <h2 className="mb-1 font-bold">CZĘŚĆ II</h2>
          <table className="w-full border-collapse">
            <tbody>
              <tr>
                <Cell head className="w-1/2">
                  DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ
                  <Fn sheet={r.sheet_type} k="conv" />
                </Cell>
                <Cell>{r.conversation_date ? `${fmtDate(r.conversation_date)} (dd.mm.rrrr)` : ""}</Cell>
              </tr>
              <tr>
                <Cell head>OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE</Cell>
                <Cell>
                  OD
                  <Fn sheet={r.sheet_type} k="from" />: {fmtDate(r.period_start)} &nbsp; DO
                  <Fn sheet={r.sheet_type} k="to" />: {fmtDate(r.period_end)}
                </Cell>
              </tr>
            </tbody>
          </table>

          <table className="mt-3 w-full border-collapse text-[11px]">
            <thead>
              <tr>
                <Cell head className="w-[34%]">
                  KRYTERIA OBOWIĄZKOWE
                </Cell>
                {SCALE.map((sc) => (
                  <Cell head key={sc.value} className="text-center">
                    {sc.label}
                    <br />
                    {sc.value} {sc.value === 1 ? "punkt" : sc.value < 5 ? "punkty" : "punktów"}
                  </Cell>
                ))}
              </tr>
            </thead>
            <tbody>
              {mandatory.map((c) => (
                <tr key={c.criterion_id}>
                  <Cell>{c.name}</Cell>
                  {SCALE.map((sc) => (
                    <Cell key={sc.value} className="text-center">
                      <X on={c.score === sc.value} />
                    </Cell>
                  ))}
                </tr>
              ))}
              <tr>
                <Cell head>
                  KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO
                  <Fn sheet={r.sheet_type} k="extra2" />
                </Cell>
                <Cell head className="text-center" >
                  OCENA CZĄSTKOWA
                  <Fn sheet={r.sheet_type} k="partial" />
                </Cell>
                {SCALE.slice(1).map((sc) => (
                  <Cell head key={sc.value} />
                ))}
              </tr>
              {[0, 1, 2].map((i) => {
                const c = additional[i];
                return (
                  <tr key={i} className="h-6">
                    <Cell>{c ? c.name : i === 0 && additional.length === 0 ? "brak" : ""}</Cell>
                    {SCALE.map((sc) => (
                      <Cell key={sc.value} className="text-center">
                        {c && <X on={c.score === sc.value} />}
                      </Cell>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2">
            Średnia arytmetyczna z ocen cząstkowych przyznanych za poszczególne kryteria oceny: <strong>{s ? s.average.toFixed(2).replace(".", ",") : ""}</strong>
          </p>

          <h3 className="mt-3 font-bold">PRZYZNANIE OCENY</h3>
          <p className="text-[11px]">Należy wstawić znak „X” w odpowiednie pole</p>
          <table className="w-full border-collapse text-[11px]">
            <thead>
              <tr>
                <Cell head className="w-10" />
                <Cell head>Liczba punktów stanowiąca średnią arytmetyczną ze wszystkich ocen cząstkowych</Cell>
                <Cell head>Ogólny poziom spełnienia kryteriów oceny</Cell>
              </tr>
            </thead>
            <tbody>
              {LEVELS.map(([range, level]) => (
                <tr key={level}>
                  <Cell className="text-center">
                    <X on={!!s?.complete && s.level === level} />
                  </Cell>
                  <Cell>{range}</Cell>
                  <Cell>{level}</Cell>
                </tr>
              ))}
            </tbody>
          </table>
          <table className="mt-3 w-full border-collapse">
            <tbody>
              <tr>
                <Cell head colSpan={4} className="text-center">
                  OCENA OKRESOWA W SŁUŻBIE CYWILNEJ
                </Cell>
              </tr>
              <tr>
                <Cell className="w-1/4">
                  POZYTYWNA
                  <Fn sheet={r.sheet_type} k="pos" />
                </Cell>
                <Cell className="w-1/4 text-center">
                  <X on={s?.result === "pozytywna"} />
                </Cell>
                <Cell className="w-1/4">
                  NEGATYWNA
                  <Fn sheet={r.sheet_type} k="neg" />
                </Cell>
                <Cell className="w-1/4 text-center">
                  <X on={s?.result === "negatywna"} />
                </Cell>
              </tr>
            </tbody>
          </table>

          <h3 className="mt-3 font-bold">
            UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ
            <Fn sheet={r.sheet_type} k="just" />
          </h3>
          <div className="min-h-[24mm] whitespace-pre-line border border-black p-2">
            {r.justification}
            {r.criteria.some((c) => c.justification) && (
              <ul className="mt-1 list-none">
                {r.criteria
                  .filter((c) => c.justification)
                  .map((c) => (
                    <li key={c.criterion_id} className="mt-1">
                      <em>{c.name}</em> – {c.justification}
                    </li>
                  ))}
              </ul>
            )}
          </div>

          <h3 className="mt-3 font-bold">
            WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO
            <Fn sheet={r.sheet_type} k="ipr" />
          </h3>
          <div className="min-h-[20mm] whitespace-pre-line border border-black p-2">{r.ipr_conclusions}</div>

          {civil && (
            <table className="mt-3 w-full border-collapse break-inside-avoid">
              <tbody>
                <tr>
                  <Cell head colSpan={3}>
                    DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ
                  </Cell>
                </tr>
                <tr>
                  <Cell>
                    Ocena
                    <Fn sheet={r.sheet_type} k="prevResult" />: {r.prev_result ?? ""}
                  </Cell>
                  <Cell>
                    Poziom
                    <Fn sheet={r.sheet_type} k="prevLevel" />: {r.prev_result === "brak" ? "" : (r.prev_level ?? "")}
                  </Cell>
                  <Cell>Data sporządzenia: {r.prev_result === "brak" ? "" : fmtDate(r.prev_date)}</Cell>
                </tr>
              </tbody>
            </table>
          )}

          <table className="mt-3 w-full border-collapse break-inside-avoid">
            <tbody>
              <tr>
                <Cell head colSpan={6}>
                  CZY DO OCENY OKRESOWEJ DOŁĄCZONO WNIOSEK O PRZYZNANIE KOLEJNEGO STOPNIA SŁUŻBOWEGO?
                  <Fn sheet={r.sheet_type} k="request" />
                </Cell>
              </tr>
              <tr>
                <Cell>TAK</Cell>
                <Cell className="w-8 text-center">
                  <X on={r.promotion_request === "tak"} />
                </Cell>
                <Cell>NIE</Cell>
                <Cell className="w-8 text-center">
                  <X on={r.promotion_request === "nie"} />
                </Cell>
                <Cell>NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)</Cell>
                <Cell className="w-8 text-center">
                  <X on={r.promotion_request === "nie_dotyczy"} />
                </Cell>
              </tr>
            </tbody>
          </table>

          <div className="break-inside-avoid">
            <table className="mt-3 w-full border-collapse">
              <tbody>
                <People title="DANE OCENIAJĄCEGO" p={r.reviewer_form} sheet={r.sheet_type} />
              </tbody>
            </table>
            <Sign place={r.reviewer_place} date={r.reviewer_signed_at} label="podpis oceniającego" method={r.signature_method} />
          </div>

          <div className="mt-3 break-inside-avoid">
            <p>Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami dotyczącymi indywidualnego programu rozwoju zawodowego.</p>
            <Sign place={r.employee_place} date={r.ack_fiction ? null : r.acknowledged_at} label="podpis ocenianego" name={r.employee.full_name} method={r.signature_method} />
            {r.ack_fiction && (
              <p className="mt-1 text-[11px]">
                Adnotacja: stwierdzono doręczenie informacji o ocenie ({fmtDate(r.acknowledged_at)}) bez potwierdzenia zapoznania przez ocenianego. {r.ack_fiction_note}
              </p>
            )}
          </div>

          <div className="mt-3 border border-black p-2 text-[11px]">
            <strong>Pouczenie</strong>
            <br />
            Na podstawie art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną,
            sprzeciw do {r.office.objection_body}
            {r.sheet_type !== "A" && <Fn sheet={r.sheet_type} k="objection" />}.
          </div>
          <Footnotes sheet={r.sheet_type} keys={["conv", "from", "to", "partial", "extra2", "pos", "neg", "just", "ipr", "prevResult", "prevLevel", "request", "objection"]} />
        </section>

        {/* ------------------------------------------------ CZĘŚĆ III */}
        {civil && r.promotion_request === "tak" && (
          <section className="break-before-page">
            <h2 className="mb-1 font-bold">CZĘŚĆ III</h2>
            <p className="text-[11px]">
              Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko w sytuacji skorzystania przez oceniającego z możliwości przewidzianej w art.
              89 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej.
              <Fn sheet={r.sheet_type} k="part3" />
            </p>
            <table className="mt-2 w-full border-collapse">
              <tbody>
                <tr>
                  <Cell head colSpan={2}>
                    DANE URZĘDNIKA SŁUŻBY CYWILNEJ
                  </Cell>
                </tr>
                {(
                  [
                    ["Imię", r.employee_form.first_name],
                    ["Nazwisko", r.employee_form.last_name],
                    ["Rok mianowania", r.appointment_year ?? ""],
                    ["Posiadany stopień służbowy", r.civil_grade_label ?? r.civil_grade ?? ""],
                    ["Data przyznania stopnia służbowego", fmtDate(r.civil_grade_date)],
                  ] as const
                ).map(([k, v]) => (
                  <tr key={k}>
                    <Cell className="w-1/3">{k}</Cell>
                    <Cell>{v}</Cell>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3 className="mt-3 font-bold">WNIOSEK O PRZYZNANIE URZĘDNIKOWI SŁUŻBY CYWILNEJ KOLEJNEGO STOPNIA SŁUŻBOWEGO</h3>
            <p>
              W związku z uzyskaniem przez Panią/Pana <strong>{r.employee.full_name}</strong> pozytywnej oceny okresowej, na podstawie art. 89 ust. 1 ustawy z dnia 21
              listopada 2008 r. o służbie cywilnej wnioskuję o przyznanie <strong>{r.promotion_target ?? "……"}</strong> stopnia służbowego.
            </p>
            <h3 className="mt-3 font-bold">UMOTYWOWANIE WNIOSKU</h3>
            <div className="min-h-[30mm] whitespace-pre-line border border-black p-2">{r.promotion_justification}</div>
            <Sign place={r.reviewer_place} date={r.reviewer_signed_at} label="podpis oceniającego" name={r.reviewer.full_name} nameLabel="imię i nazwisko lub pieczątka oceniającego" method={r.signature_method} />
            <Footnotes sheet={r.sheet_type} keys={["part3"]} />
          </section>
        )}

        {/* ------------------------------------------------ § 8: pisemne zawiadomienie o zmianie terminu (kopia do arkusza) */}
        {r.due_date_history
          .filter((h) => h.reason.includes("art. 81 ust. 8") && !h.reason.includes("zmiana oceniającego na:"))
          .map((h, i) => (
            <section key={i} className="break-before-page">
              <div className="flex justify-between">
                <div>{r.office.name}</div>
                <div>
                  {r.office.city}, {fmtDate(h.at)}
                </div>
              </div>
              <div className="mt-6 ml-auto w-1/2">
                Pani/Pan
                <br />
                <strong>{r.employee.full_name}</strong>
                <br />
                {r.employee_form.position}
              </div>
              <h2 className="mt-8 text-center font-bold">ZAWIADOMIENIE O ZMIANIE TERMINU SPORZĄDZENIA OCENY OKRESOWEJ</h2>
              <p className="mt-4 text-justify">
                Na podstawie § 8 rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników
                służby cywilnej i pracowników służby cywilnej (Dz. U. poz. 470) zawiadamiam, że termin sporządzenia Pani/Pana oceny okresowej na piśmie
                {h.from ? <> ustalony na dzień {fmtDate(h.from)}</> : null} został zmieniony na dzień <strong>{fmtDate(h.date)}</strong>.
              </p>
              <p className="mt-2">Podstawa zmiany: {h.reason}.</p>
              {h.note && <p className="mt-2">Uzasadnienie: {h.note}</p>}
              <Sign place={r.office.city} date={h.at} label="podpis oceniającego" name={r.reviewer.full_name} nameLabel="imię i nazwisko lub pieczątka oceniającego" method={r.signature_method} />
              <p className="mt-6 text-[10px]">Kopię pisma dołącza się do arkusza oceny okresowej (§ 8 rozporządzenia).</p>
            </section>
          ))}
      </div>
    </div>
  );
}
