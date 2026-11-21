# ADR 0002: Embeddingi w kolumnie JSON zamiast pgvector (na etapie MVP)

**Status:** przyjęta (do rewizji przy większym korpusie)

## Kontekst
ARCHITECTURE.md zakładał pgvector. Korpus RAG w MVP to jedno rozporządzenie, czyli ~35 fragmentów. Aplikacja ma też działać lokalnie na SQLite, bez Dockera.

## Decyzja
Embeddingi (bge-m3 z Ollamy) są zapisywane w kolumnie JSON. Wyszukiwanie liczy podobieństwo cosinusowe w numpy z domieszką wyszukiwania leksykalnego (hybryda 0,8 / 0,2). Bez modelu embeddingów działa samo wyszukiwanie leksykalne (prefiksy słów ważone IDF).

## Konsekwencje
- Ten sam kod działa na SQLite i Postgresie, a obraz Postgresa nie wymaga rozszerzeń.
- Przy korpusie powyżej kilku tysięcy fragmentów (ustawa, opisy stanowisk wszystkich urzędów) należy przejść na `pgvector`: zmienić typ kolumny `doc_chunk.embedding` i użyć operatora `<=>`.
