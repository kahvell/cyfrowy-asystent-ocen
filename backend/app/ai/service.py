"""Wspólna ścieżka wywołania modelu: prompt -> (pseudonimizacja) -> LLM -> walidacja -> (depseudonimizacja).

Jeśli model jest niedostępny lub w trybie `fake`, używana jest heurystyka danego pipeline'u.
W `ai_suggestion.model` zapisujemy, co faktycznie wygenerowało treść.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel

from app.ai.provider import LLMError, get_provider
from app.ai.pseudonymizer import Pseudonymizer
from app.config import settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_env = Environment(loader=FileSystemLoader(PROMPTS_DIR), undefined=StrictUndefined, autoescape=False)


def latest_prompt(name: str) -> str:
    """Zwraca nazwę najnowszej wersji szablonu, np. 'draft_justification.v2'."""
    versions = sorted(PROMPTS_DIR.glob(f"{name}.v*.j2"), key=lambda p: int(p.stem.rsplit(".v", 1)[1]))
    if not versions:
        raise FileNotFoundError(f"Brak promptu {name}")
    return versions[-1].stem


def render_prompt(name: str, **ctx) -> tuple[str, str]:
    version = latest_prompt(name)
    return _env.get_template(f"{version}.j2").render(**ctx), version


def run_structured(
    prompt: str,
    schema: type[T],
    heuristic: Callable[[], T],
    people: list[str] | None = None,
) -> tuple[T, str]:
    provider = get_provider()
    if provider.is_fake:
        return heuristic(), "heuristic"

    pseudo = Pseudonymizer(people or []) if settings.pseudonymize else None
    sent = pseudo.apply(prompt) if pseudo else prompt
    try:
        result = provider.complete_json(sent, schema)
    except LLMError as exc:
        if settings.llm_heuristic_fallback:
            log.warning("LLM niedostępny, używam heurystyki: %s", exc)
            return heuristic(), "heuristic (fallback: model niedostępny)"
        raise HTTPException(502, f"Asystent AI jest chwilowo niedostępny: {exc}") from exc

    if pseudo:
        result = schema.model_validate_json(pseudo.revert(result.model_dump_json()))
    return result, provider.model
