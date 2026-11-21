# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# czcionka DejaVu - polskie znaki w generowanym arkuszu PDF (reportlab)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# zależności w osobnej warstwie - zmiana kodu nie pobiera ich ponownie;
# cache pip między buildami - dodanie jednej biblioteki nie pobiera wszystkich od nowa
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && pip install -r requirements.txt

COPY app ./app
RUN pip install --no-cache-dir --no-deps .
COPY seed ./seed

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
