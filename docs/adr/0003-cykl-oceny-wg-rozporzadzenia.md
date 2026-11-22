# ADR 0003: Cykl oceny zgodny z kolejnością z rozporządzenia

**Status:** przyjęta

## Kontekst
Pierwotny diagram w ARCHITECTURE.md zakładał kolejność `draft → submitted → discussed → final`, gdzie „submitted” oznaczało złożenie oceny. Według § 10 rozporządzenia rozmowa oceniająca odbywa się **przed** sporządzeniem oceny na piśmie, a według § 11 ust. 2 oceniający uwzględnia wnioski z rozmowy.

## Decyzja
- `draft`: przygotowanie oceny,
- `submitted`: gotowa do rozmowy (wymaga braku krytycznych ostrzeżeń kontroli jakości),
- `discussed`: po rozmowie oceniającej (data rozmowy); ocenę można jeszcze skorygować,
- `final`: ocena sporządzona na piśmie (wymaga kompletu ocen, uzasadnienia przy ocenie negatywnej i wniosków do IPRZ).

Samoocenę pracownik może wypełnić do chwili zatwierdzenia oceny. Przełożony widzi ją dopiero po przekazaniu, a pracownik widzi oceny przełożonego dopiero od statusu `submitted`.

## Konsekwencje
Status w systemie odpowiada czynnościom z rozporządzenia, a blokady przejść egzekwują jego wymogi.
