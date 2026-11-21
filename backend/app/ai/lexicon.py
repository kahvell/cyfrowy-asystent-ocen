"""Słowniki używane przez heurystyki (tryb bez modelu) i przez reguły kontroli jakości."""

import re

POSITIVE = [
    "świetn", "bardzo dobr", "doskonał", "sprawn", "terminow", "pochwał", "podziękow", "wzorow",
    "skuteczn", "profesjonaln", "zaangażow", "samodzieln", "inicjatyw", "bezbłędn", "przed termin",
    "usprawni", "zaproponował", "poprowadził", "rzeteln", "sukces", "pozytywn", "docenil", "docenił",
    "wsparł", "pomógł", "pomogła", "przygotował", "zrealizował", "wdrożył", "ukończył", "dobrze",
]
NEGATIVE = [
    "spóźni", "opóźni", "błęd", "błąd", "nie dotrzym", "skarg", "zapomniał", "nie przygotow",
    "niedokładn", "pomyłk", "uchybieni", "przekroczył termin", "przekroczono termin", "nieuprzejm",
    "zaniedba", "problem", "nie odpowiedział", "brak", "nieczyteln", "chaotyczn", "konflikt",
    "musiał poprawi", "trzeba było poprawi", "wymagał poprawek", "nie zgłosił", "niejasn",
]

# Ogólniki, które nic nie mówią o zachowaniu pracownika
VAGUE_PHRASES = [
    "pracuje dobrze", "dobry pracownik", "dobra pracownica", "bez zastrzeżeń", "w porządku", "jest ok",
    "wywiązuje się z obowiązków", "radzi sobie", "stara się", "nie mam uwag", "poprawnie", "zgodnie z oczekiwaniami",
    "jak zawsze", "solidny pracownik", "solidna pracownica", "ogólnie dobrze", "bardzo dobry pracownik",
    "bardzo dobra pracownica", "zasługuje na wysoką ocenę",
]

# Język oceniający osobę zamiast zachowań / stereotypy / dane wrażliwe (wzorzec, kategoria, wskazówka)
BIAS_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(p, re.I), cat, hint)
    for p, cat, hint in [
        (r"\bemocjonaln\w*", "cecha osobowości", "opisz konkretne zachowanie w konkretnej sytuacji"),
        (r"\bhisteryczn\w*", "stereotyp płciowy", "unikaj nacechowanych określeń - opisz zachowanie"),
        (r"\bapodyktyczn\w*", "cecha osobowości", "opisz, jak podejmowane były decyzje i z jakim skutkiem"),
        (r"\bkapryśn\w*", "stereotyp płciowy", "opisz zachowanie i jego wpływ na pracę"),
        (r"\bmił[aye]\b|\bsympatyczn\w*|\burocz\w*|\bładn\w*", "cecha osobowości / wygląd",
         "ocena dotyczy wykonywania obowiązków, nie sympatii ani wyglądu"),
        (r"\bkobiec\w*|\bmęsk\w*|\bjak na kobietę\b|\bjak na mężczyznę\b", "stereotyp płciowy",
         "płeć nie jest kryterium oceny"),
        (r"\bmacierzyńsk\w*|\bojcowsk\w*|\bciąż\w*|\bdzieci\b|\brodzicielsk\w*", "sytuacja rodzinna",
         "sytuacja rodzinna nie może wpływać na ocenę"),
        (r"\bzwolnieni\w* lekarsk\w*|\bL4\b|\bchorob\w*|\bchorował\w*", "zdrowie",
         "nieobecności usprawiedliwione nie są kryterium oceny; dane o zdrowiu to dane szczególnej kategorii"),
        (r"\bmłod[ayeyi]\w*\b|\bstar(y|a|szy|sza|sze|szego)\b|\bw tym wieku\b|\bprzed emerytur\w*", "wiek",
         "wiek nie jest kryterium oceny"),
        (r"\bosobowoś\w*|\btemperament\w*|\bz charakter\w*", "cecha osobowości",
         "kryteria z rozporządzenia opisują zachowania - odnieś się do nich"),
        (r"\bwyznani\w*|\breligi\w*|\bpoglądy\b", "dane wrażliwe", "nie uwzględniaj przekonań w ocenie"),
    ]
]


def sentiment_of(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def match_criteria(text: str, keywords_by_code: dict[str, list[str]], top: int = 3) -> list[tuple[str, float]]:
    t = text.lower()
    scored = []
    for code, kws in keywords_by_code.items():
        hits = sum(1 for k in kws if k in t)
        if hits:
            scored.append((code, min(0.95, 0.45 + 0.15 * hits)))
    scored.sort(key=lambda x: -x[1])
    return scored[:top]


def find_vague(text: str) -> list[str]:
    t = text.lower()
    return [p for p in VAGUE_PHRASES if p in t]


def find_bias(text: str) -> list[tuple[str, str, str]]:
    out = []
    for pattern, cat, hint in BIAS_PATTERNS:
        m = pattern.search(text)
        if m:
            out.append((m.group(0), cat, hint))
    return out
