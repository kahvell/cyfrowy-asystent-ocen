# ADR 0001: Heurystyki jako tryb bez modelu i fallback

**Status:** przyjęta

## Kontekst
System ma działać w ~1740 urzędach o różnej infrastrukturze. Nie każdy urząd od razu postawi serwer z GPU. Jury klonujące repo też nie będzie miało modelu. Testy w CI nie mogą wymagać kluczy API.

## Decyzja
Każdy pipeline AI ma deterministyczną heurystykę o tym samym schemacie wyjścia (Pydantic):
- `LLM_MODE=fake`: zawsze heurystyka (CI, demo offline),
- `LLM_MODE=local/external`: model; jeśli jest niedostępny lub dwa razy zwrócił niepoprawny JSON, używana jest heurystyka (`LLM_HEURISTIC_FALLBACK=true`).

Przed wywołaniem Ollamy wykonywany jest szybki test dostępności (`/api/tags`, timeout 2 s, cache 30 s), żeby UI nie czekał na timeout.

## Konsekwencje
- Aplikacja zawsze działa, a jakość tekstu rośnie po podłączeniu modelu.
- W `ai_suggestion.model` zapisujemy faktyczne źródło treści (`heuristic (fallback: model niedostępny)`), a UI to pokazuje. To wymóg przejrzystości z AI Act.
