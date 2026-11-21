"""Abstrakcja dostawcy modelu językowego.

- LiteLLMProvider: jedna klasa dla Ollamy (PLLuM / Bielik), vLLM i zewnętrznych API.
- FakeLLMProvider: bez modelu; pipeline'y używają wtedy deterministycznych heurystyk
  (testy, CI bez kluczy API, demo offline).
"""

import json
import logging
import re
import time
import urllib.request
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = (
    "Jesteś asystentem przełożonego w polskiej administracji rządowej (służba cywilna), "
    "pomagającym rzetelnie przygotować ocenę okresową zgodnie z rozporządzeniem Prezesa Rady Ministrów "
    "z 4 kwietnia 2016 r. Piszesz po polsku, rzeczowo, opisując zachowania i fakty, nie cechy osobowości. "
    "Nigdy nie wymyślasz faktów, których nie ma w danych wejściowych. AI tylko proponuje - decyzję podejmuje człowiek."
)


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str
    is_fake: bool

    def complete_json(self, prompt: str, schema: type[T]) -> T: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _extract_json(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Brak obiektu JSON w odpowiedzi modelu")
    return text[start : end + 1]


class LiteLLMProvider:
    name = "litellm"
    is_fake = False

    def __init__(self, model: str, embedding_model: str | None, api_key: str | None, ollama_base: str):
        self.model = model
        self.embedding_model = embedding_model
        self.api_key = api_key
        self.ollama_base = ollama_base

    _ollama_ok: tuple[float, bool] | None = None  # (czas sprawdzenia, wynik)

    def _ensure_reachable(self, model: str) -> None:
        """Szybki test dostępności Ollamy (cache 30 s), żeby przy wyłączonym modelu
        od razu przejść na heurystyki zamiast czekać na timeout."""
        if not model.startswith(("ollama/", "ollama_chat/")):
            return
        now = time.monotonic()
        if self._ollama_ok is None or now - self._ollama_ok[0] > 30:
            try:
                with urllib.request.urlopen(f"{self.ollama_base.rstrip('/')}/api/tags", timeout=2) as r:
                    ok = r.status == 200
            except (OSError, ValueError):
                ok = False
            self._ollama_ok = (now, ok)
        if not self._ollama_ok[1]:
            raise LLMError(f"Ollama niedostępna pod {self.ollama_base}")

    def _kwargs(self, model: str) -> dict:
        kw: dict = {"timeout": settings.llm_timeout, "num_retries": 0}
        if model.startswith(("ollama/", "ollama_chat/")):
            kw["api_base"] = self.ollama_base
        elif self.api_key:
            kw["api_key"] = self.api_key
        return kw

    def complete_json(self, prompt: str, schema: type[T]) -> T:
        self._ensure_reachable(self.model)
        import litellm

        litellm.drop_params = True
        schema_txt = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": f"{SYSTEM_PROMPT}\n\nOdpowiadasz WYŁĄCZNIE jednym obiektem JSON zgodnym z tym schematem "
                f"(bez komentarzy, bez markdown):\n{schema_txt}",
            },
            {"role": "user", "content": prompt},
        ]
        last_err: Exception | None = None
        for attempt in range(2):  # jedna ponowna próba z komunikatem błędu walidacji
            try:
                resp = litellm.completion(
                    model=self.model,
                    messages=messages,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    **self._kwargs(self.model),
                )
                content = resp.choices[0].message.content or ""
            except Exception as exc:  # błąd sieci / modelu - nie ma sensu ponawiać
                raise LLMError(f"Model niedostępny: {exc}") from exc
            try:
                return schema.model_validate_json(_extract_json(content))
            except (ValidationError, ValueError) as exc:
                last_err = exc
                log.warning("Niepoprawny JSON od modelu (próba %s): %s", attempt + 1, exc)
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"Odpowiedź nie przeszła walidacji: {exc}. Zwróć poprawiony JSON zgodny ze schematem.",
                    },
                ]
        raise LLMError(f"Model zwrócił niepoprawny JSON: {last_err}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embedding_model:
            raise LLMError("Brak modelu embeddingów")
        self._ensure_reachable(self.embedding_model)
        import litellm

        try:
            resp = litellm.embedding(model=self.embedding_model, input=texts, **self._kwargs(self.embedding_model))
        except Exception as exc:
            raise LLMError(f"Embeddingi niedostępne: {exc}") from exc
        return [d["embedding"] for d in resp.data]


class FakeLLMProvider:
    name = "fake"
    model = "heuristic"
    is_fake = True

    def complete_json(self, prompt: str, schema: type[T]) -> T:  # pragma: no cover - nieużywane
        raise LLMError("FakeLLMProvider nie generuje tekstu - pipeline używa heurystyki")

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise LLMError("FakeLLMProvider nie liczy embeddingów")


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.llm_mode == "fake":
            _provider = FakeLLMProvider()
        else:
            _provider = LiteLLMProvider(
                model=settings.llm_model,
                embedding_model=settings.embedding_model or None,
                api_key=settings.llm_api_key,
                ollama_base=settings.ollama_base_url,
            )
    return _provider


def set_provider(provider: LLMProvider | None) -> None:
    """Do testów: podmiana dostawcy."""
    global _provider
    _provider = provider
