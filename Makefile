.PHONY: up up-local down dev-backend dev-frontend test lint seed-reset

up:            ## cały system w Dockerze (model: wg .env, bez modelu -> reguły)
	docker compose up --build

up-local:      ## w pełni offline z lokalnym modelem (Ollama)
	docker compose --profile local-llm up --build

down:
	docker compose down

dev-backend:   ## backend bez Dockera (SQLite)
	cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm install && npm run dev

test:
	cd backend && LLM_MODE=fake .venv/bin/pytest -q

lint:
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

seed-reset:    ## nowa baza demo (SQLite)
	rm -f backend/app.db
