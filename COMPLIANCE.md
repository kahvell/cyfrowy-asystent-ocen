# Zgodność systemu z materiałami wytycznych

Audyt zgodności „Cyfrowego Asystenta Ocen Okresowych” z materiałami organizatora
(foldery `1. Akty prawne` – `6. Materiały dodatkowe`). Data audytu: 2026-11-21.

Wniosek ogólny: **system jest zgodny z wymaganiami** we wszystkich sześciu obszarach.
Jedyna istotna luka to brak serwerowego generowania arkusza do pliku (PDF/DOCX) —
wydruk odbywał się wyłącznie w przeglądarce. Luka została domknięta przez endpoint
`GET /reviews/{id}/form.pdf` (patrz sekcja „Zmiany po audycie”).

---

## Folder 1 — Akty prawne

Rozporządzenie PRM z 4 kwietnia 2016 r. (Dz.U. 2016 poz. 470) wraz z załącznikami nr 1–4
oraz wyciąg z ustawy o służbie cywilnej (art. 81, 82, 83, 89).

| Wymóg prawny | Implementacja | Status |
|---|---|---|
| § 4 — kryteria obowiązkowe per arkusz (A/B/C) | `backend/seed/criteria.json`, `mandatory_criteria()` | zgodne |
| § 5 — rozmowa rozpoczynająca, max 3 kryteria dodatkowe | `services/reviews.py` (`MAX_ADDITIONAL_CRITERIA=3`), walidacja w `api/reviews.py` | zgodne |
| § 11 — skala 1/3/5/7/9, średnia arytmetyczna, przedziały poziomów | `services/scoring.py` (`SCALE`, `compute_outcome`) | zgodne |
| § 11 ust. 3 — uzasadnienie obligatoryjne przy ocenie negatywnej | `api/reviews.py` (walidacja przy finalizacji / po sprzeciwie) | zgodne |
| art. 81 ust. 1 — kto podlega ocenie (mianowanie / czas nieokreślony) | `services/cycle.py` (`subject_to_review`) | zgodne |
| art. 81 ust. 4/7/8/9 — 24 mies., przedłużenie o nieobecność, zmiana terminu, powtórna po 6 mies. | `services/deadlines.py` (`RULES`) | zgodne |
| art. 83 — sprzeciw 7 dni, rozpatrzenie 14 dni, zmiana / ponowne sporządzenie | `api/reviews.py` (`file_objection`, `decide_objection`) | zgodne |
| art. 89 — stopnie służbowe, obligatoryjna promocja po 2 ocenach na 2 najwyższych poziomach | `services/process.py` (`obligatory_promotion`, `grade_label`, `promotion_target`) | zgodne |

Reguły liczbowe i proceduralne są wyliczane kodem (nie konfiguracją ręczną) i odzwierciedlają przepisy.

## Folder 2 — Przypadki użycia

Opis przypadków użycia i warunki brzegowe (docx) oraz modele BPMN/XPDL
(`3. Schemat procesu/out/`) z rolami: ZARZĄDZAJĄCY, OCENIAJĄCY, OCENIANY,
SYSTEM KADROWY, SYSTEM SPRAWOZDAWCZY, SCHEDULER.

Wszystkie kluczowe przypadki mają pokrycie w API (`api/reviews.py` i pozostałe routery):

- rozpoczęcie cyklu, wyznaczenie kryteriów, rozmowa rozpoczynająca (2-etapowe potwierdzenie) —
  `criteria/confirm`, `criteria/acknowledge`;
- ocena i przekazanie do zapoznania — `submit`, `discussed`, `finalize`;
- zmiana terminu oceny (powody art. 81 ust. 8) — `due-date`, `due-date-requests`;
- sprzeciw i jego rozpatrzenie — `objection`, `objection/decision`;
- fikcja zapoznania — `ack-fiction`;
- wniosek o stopień / promocja — pola `promotion_request`, logika w `services/process.py`;
- powtórna ocena po negatywnej — `is_repeat_review`, `repeat_review_date`;
- tryb korekty błędów przez administratora — `patch_review` + `corrections`;
- CRUD pracownika, podległości, nieobecności, zastępstwa, statystyki/eksport z k-anonimowością,
  archiwizacja, wydruk — `api/admin.py`, `api/hr_functions.py`, `api/reminders.py`.

Status: **zaimplementowane**, łącznie z warunkami brzegowymi (sprzeciw po terminie, zakaz obniżenia
oceny po sprzeciwie, blokada wniosku o stopień przy ocenie negatywnej).

## Folder 3 — Schemat procesu

Skrócony opis procesu, etapy, 9 stopni służbowych, obligatoryjna promocja.

- Etapy `criteria → observation → draft → submitted → discussed → final → acknowledged`
  (gałąź `objection`) zdefiniowane w `services/process.py` (`STAGES`) i egzekwowane przez `_transition`.
- Cykl 24-miesięczny oraz „koniec cyklu → początek następnego” — `services/cycle.py`.
- Role w procesie odwzorowane w uprawnieniach endpointów (`get_review_for(..., manage=)`, rola `hr`/`admin`).

Status: **zgodne.**

## Folder 4 — Formularze ocen

Szczegółowe mapy pól arkuszy A/B/C (reguły edytowalności/blokowania na każdym etapie, wartości
domyślne, przypisy) oraz wersja zautomatyzowana xlsx (Część I/II/III).

- Struktura Części I/II/III w modelu `Review` (`app/models.py`).
- Blokady edytowalności per etap — `api/reviews.py` (`CRITERIA_FIELDS` / `EVALUATION_FIELDS`,
  HTTP 409 przy nielegalnej zmianie pola).
- Formularz frontendowy `frontend/src/components/process.tsx`; wydruk
  `frontend/src/app/reviews/[id]/print/page.tsx` (arkusz A = zał. 2, B = zał. 3, C = zał. 4,
  pouczenie art. 83, przypisy per arkusz).
- Domyślna miejscowość = miasto urzędu; automatyczne liczenie średniej, poziomu i wyniku.

Uwaga: pliki „wzór formularza oceny okresowej arkusz X.pdf” to skany obrazkowe (brak warstwy
tekstowej) — weryfikację oparto na mapach pól i wersji xlsx.

Status: **zgodne** co do struktury i reguł pól.

## Folder 5 — Przykładowe wypełnione formularze oceny

Przykładowe arkusze A/B/C z realnymi danymi. Render wydruku odwzorowuje układ wzoru, a przykładowe
dane mieszczą się w polach modelu (oceny cząstkowe, uzasadnienia, IPR, dane stron, część III).

Status: **zgodne.**

## Folder 6 — Materiały dodatkowe

Zasady liczenia terminów (miesiące, dni robocze, łączenie nieobecności) oraz poradnik KPRM.

`services/deadlines.py` implementuje: `add_months`, `next_working_day`, `merge_absences`, algorytm
daty Wielkanocy i polskie święta (z Wigilią od 2025 r.); wszystkie stałe w słowniku `RULES`.

Status: **zgodne.**

---

## Rozbieżności i uwagi

1. **Brak serwerowego generowania pliku** — wydruk realizowany wyłącznie w przeglądarce.
   *Domknięte:* endpoint `GET /reviews/{id}/form.pdf` generuje arkusz A/B/C w PDF (reportlab).
2. **Wyższe stanowiska (art. 52)** — system domyślnie wyłącza je z cyklu, ale dopuszcza ręczne
   założenie oceny (`explicit`) z ostrzeżeniem w odpowiedzi API. Świadome odstępstwo opisane w kodzie
   (`services/cycle.py`) i w `docs/adr/0004-proces-wg-dokumentow-kprm.md`.

Świadome odstępstwa techniczne (brak shadcn/react-hook-form, własne typy TS, wektory w JSON)
są udokumentowane w `docs/adr/` i nie wpływają na zgodność funkcjonalną.
