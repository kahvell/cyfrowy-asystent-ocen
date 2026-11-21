# ADR 0004: Proces oceny odwzorowany wg przypadków użycia i schematu pól KPRM

**Status:** przyjęta (zastępuje częściowo ADR 0003)

## Kontekst
Materiały KPRM do wyzwania (przypadki użycia, warunki brzegowe, „schemat pól formularza” arkuszy A/B/C, zasady liczenia terminów) opisują proces szerszy niż sama ocena: wyznaczenie kryteriów z potwierdzeniem obu stron, zapoznanie z oceną lub fikcję zapoznania, sprzeciw, wniosek o stopień służbowy oraz zmiany terminów.

## Decyzja
- Statusy oceny: `criteria → observation → draft → submitted → discussed → final → acknowledged`, plus `objection`.
- Każde pole arkusza ma określony etap edycji (`CRITERIA_FIELDS`, `EVALUATION_FIELDS` w `services/process.py`). Poza nim backend odrzuca zmianę (409) z komunikatem o trybie korekty przez administratora.
- Bramki potwierdzenia drugiej strony występują na etapach I (kryteria, `criteria`), IV (rozmowa oceniająca, `submitted`) i VI (zapoznanie, `final`): dopiero potwierdzenie zamyka etap i blokuje jego pola. Pola etapu IV odblokowuje zaproszenie `.ics` (`assessment_invited_at`) potwierdzone przez ocenianego (`assessment_confirmed_at`).
- Samo przejście przez etap bez bramki (np. II → III) nie blokuje powrotu: przełożony może kliknąć wcześniejszy etap i go poprawić, przy czym status procesu się nie zmienia, a przypisanie edytowalności rozstrzyga bieżący status arkusza, nie oglądany etap.
- Terminy liczy kod według materiału KPRM; wszystkie stałe są w `RULES`, więc zmiana przepisów to zmiana konfiguracji.
- Podpis to potwierdzenie w systemie (data, miejscowość, użytkownik w `audit_log`). Integracja z podpisem kwalifikowanym lub EZD jest punktem rozszerzenia.
- Zgodnie ze schematem procesu (BPMN) cykl startuje automatycznie: po wprowadzeniu pracownika przez kadry i po sporządzeniu każdej oceny („koniec cyklu oceny i początek następnego”). Zmianę oceny po uwzględnieniu sprzeciwu wprowadza dyrektor generalny w formularzu; sporządzenie po raz drugi wraca do oceniającego.
- HR widzi sporządzone arkusze (dokumentacja kadrowa, sprzeciwy), ale nie szkice ani dziennik obserwacji.

## Konsekwencje
Demo pokazuje cały proces, a jury może sprawdzić zgodność z przepisami na wydruku arkusza. Zmiana schematu bazy wymaga na razie nowej bazy (brak Alembica, ADR w sekcji 14 ARCHITECTURE.md).
