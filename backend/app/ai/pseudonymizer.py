"""Deterministyczna pseudonimizacja przed wysłaniem tekstu do zewnętrznego modelu.

Imiona i nazwiska znamy z bazy, więc nie potrzeba NER-a. Obsługujemy proste formy odmiany
(„Kowalska” → „Kowalskiej”, „Kowalską”) przez dopasowanie po rdzeniu.
Mapowanie żyje tylko w pamięci, na czas jednego requestu.
"""

import re
from dataclasses import dataclass, field

_PESEL = re.compile(r"\b\d{11}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?<!\d)(?:\+48[\s-]?)?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")


_VOWELS = "aeiouyąęó"


def _name_regex(word: str) -> str:
    """Wzorzec łapiący formy odmiany: Anna -> Ann\\w{0,4} (Anny, Annie, Anną),
    Kowalska -> Kowalsk\\w{0,4}, Nowak -> Nowak\\w{0,4} (Nowaka, Nowakiem)."""
    stem = word[:-1] if len(word) > 3 and word[-1].lower() in _VOWELS else word
    return rf"\b{re.escape(stem)}\w{{0,4}}\b"


@dataclass
class Pseudonymizer:
    people: list[str]
    mapping: dict[str, str] = field(default_factory=dict)  # token -> oryginał

    def _person_patterns(self) -> list[tuple[re.Pattern[str], str]]:
        patterns: list[tuple[re.Pattern[str], str]] = []
        for i, full in enumerate(sorted(set(self.people), key=len, reverse=True), start=1):
            token = f"[OSOBA_{i}]"
            self.mapping[token] = full
            parts = full.split()
            if len(parts) >= 2:
                first, last = parts[0], parts[-1]
                # pełne imię i nazwisko (z odmianą), samo nazwisko, samo imię
                patterns.append((re.compile(rf"{_name_regex(first)}\s+{_name_regex(last)}"), token))
                patterns.append((re.compile(_name_regex(last)), token))
                patterns.append((re.compile(_name_regex(first)), token))
            else:
                patterns.append((re.compile(_name_regex(full)), token))
        return patterns

    def apply(self, text: str) -> str:
        for pattern, token in self._person_patterns():
            text = pattern.sub(token, text)
        text = _PESEL.sub("[PESEL]", text)
        text = _EMAIL.sub("[EMAIL]", text)
        text = _PHONE.sub("[TELEFON]", text)
        return text

    def revert(self, text: str) -> str:
        for token, original in self.mapping.items():
            text = text.replace(token, original)
        return text
