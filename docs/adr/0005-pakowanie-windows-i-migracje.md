# ADR 0005: Pakowanie na Windows 11 i przetrwanie danych przy aktualizacji

**Status:** przyjęta

## Kontekst
System ma działać w urzędzie: instalacja na Windows 11 i praca w przeglądarce, bez chmury (założenie 1 i 2 z `ARCHITECTURE.md`). Deployment jest dziś wyłącznie kontenerowy (`docker-compose.yml`), a kolejne wersje mają być wdrażane w urzędach, które mają już dane pracowników i sporządzone oceny. Potrzebna jest więc odpowiedź na dwa pytania: jak dostarczyć aplikację na Windows 11 i jak zagwarantować, że dane w Postgresie przetrwają aktualizację.

Ustalenia z przeglądu kodu, które wpłynęły na decyzję:

- backend **nie zapisuje nic poza bazą danych** — brak uploadów i plików użytkownika; PDF arkusza, zestawienia CSV i zaproszenia `.ics` są generowane w locie;
- trwały stan to `pgdata` (Postgres), `.env` (sekrety) oraz wolumen `ollama` (modele, odtwarzalne);
- `init_db()` wykonuje przy starcie tylko `alembic upgrade head` — nie ma automatycznego cofania schematu;
- `seed_reference()` wstawia kryteria i szkolenia **tylko gdy tabele są puste**, więc zmiana przepisów nie trafiłaby do działającej bazy;
- `backfill_embeddings()` uzupełnia tylko brakujące wektory — zmiana `EMBEDDING_MODEL` nie unieważnia starych;
- w repozytorium **nie ma skryptów z `docker compose down -v`** — jedyne wywołanie `docker compose down` jest w `Makefile` (bez `-v`).

## Decyzja

1. **Formą dystrybucji pozostają kontenery OCI, nie instalator `.exe`.** Na Windows 11 używamy Docker Desktop albo — ze względu na licencję w administracji publicznej — Podman Desktop / Rancher Desktop. Uruchomienie zapewnia `start.ps1` (sprawdzenie środowiska, `.env`, `compose up -d --build`, oczekiwanie na `/health`, otwarcie przeglądarki). Porzucamy natywne pakowanie (PyInstaller + portable Postgres): koszt przewyższa korzyść, a licencję Dockera rozwiązuje Podman.
2. **Aktualizuje się obrazy, nigdy wolumen danych.** Zabronione jest `docker compose down -v` i `docker volume rm` w procedurach urzędowych. Aktualizacja = nowy tag obrazu + automatyczne `alembic upgrade head` przy starcie.
3. **Backup obowiązkowo przed każdą aktualizacją.** `scripts/backup-postgres.ps1` robi `pg_dump -Fc` (zapis wewnątrz kontenera i `docker compose cp` — PowerShell nie może przekierowywać binarnych strumieni), kopiuje `.env` i zapisuje metadane: wersja aplikacji (git) + rewizja Alembica. Skrypt obsługuje też odtworzenie (`-Restore`), zatrzymując backend na czas `pg_restore`.
4. **Zmiany treści referencyjnych idą migracją danych, nie seedem.** Kryteria z `seed/criteria.json` są synchronizowane po `code` przez migrację Alembica (wzorzec: `0009_upsert_kryteria`). Ten sam wzorzec stosuje się do `trainings.json`, gdy zmiana będzie dotyczyć szkoleń.
5. **Rollback to odtworzenie backupu i powrót na poprzedni tag obrazu**, nigdy `alembic downgrade` — aplikacja cofa się tylko przez dane, bo migracje w górę nie mają gwarantowanej ścieżki odwrotnej.
6. **Zmiana modelu embeddingów wymaga ponownego zaindeksowania przepisów** (świadoma czynność przy aktualizacji, nie automat).

## Konsekwencje
Aktualizacja w urzędzie sprowadza się do: backup → podmiana tagu obrazu → `compose up -d` → weryfikacja (`/health`, logowanie, otwarcie istniejącej oceny, `SELECT version_num FROM alembic_version`) → w razie problemu restore backupu. Dane pracowników i oceny nie są dotykane; wymiana modelu AI działa na wolumenie `ollama`, który można odtworzyć pobraniem.

Koszt: każda zmiana kryteriów wymaga napisania migracji, a nie edycji JSON-a; backup i jego szyfrowanie (dane osobowe, RODO) trzeba wpisać w procedurę urzędu; `pg_dump` przy dużych bazach wymaga chwili przestoju lub uruchomienia poza godzinami pracy.

## Do dokończenia (poza zakresem tego ADR)
- `restart: unless-stopped` w `docker-compose.yml` + autostart Docker Desktop, żeby stos wracał po restarcie hosta;
- harmonogram (Windows Task Scheduler / cron) dla `python -m app.services.notify digest` i dla dziennego backupu;
- `SEED_DEMO_DATA=false` w instalacji produkcyjnej (domyślnie `true` w `config.py` — na czystej bazie utworzy dane demo);
- `extra_hosts: host.docker.internal:host-gateway` jest zapisem linuxowym — na Docker Desktop `host.docker.internal` działa natywnie, wpis wymaga weryfikacji;
- ścieżki czcionek DejaVu w `form_pdf.py` są linuxowe — tryb natywny bez Dockera wymaga dodania ścieżek Windows, inaczej PDF gubi polskie znaki;
- HTTPS / reverse proxy, gdy system ma być dostępny w sieci urzędu, a nie tylko na jednym komputerze.
