"""Skala ocen wg § 11 rozporządzenia PRM z 4 kwietnia 2016 r. (Dz.U. 2016 poz. 470).

Liczy wyłącznie kod - bez LLM.
"""

from dataclasses import dataclass

SCALE: dict[int, str] = {
    1: "znacznie poniżej oczekiwań",
    3: "poniżej oczekiwań",
    5: "na poziomie oczekiwań",
    7: "powyżej oczekiwań",
    9: "znacznie powyżej oczekiwań",
}
VALID_SCORES = frozenset(SCALE)
MAX_ADDITIONAL_CRITERIA = 3  # § 5 ust. 2


def overall_level(avg: float) -> str:
    """§ 11 ust. 1 pkt 2: przedziały średniej arytmetycznej."""
    if avg <= 2:
        return SCALE[1]
    if avg <= 4:
        return SCALE[3]
    if avg <= 6:
        return SCALE[5]
    if avg <= 8:
        return SCALE[7]
    return SCALE[9]


@dataclass(frozen=True)
class ReviewOutcome:
    average: float
    level: str
    result: str  # pozytywna | negatywna
    complete: bool


def compute_outcome(scores: list[int | None]) -> ReviewOutcome | None:
    """§ 11 ust. 1 pkt 3-4: ocena pozytywna gdy poziom >= 'na poziomie oczekiwań'
    i żadna ocena cząstkowa nie jest 'znacznie poniżej oczekiwań'."""
    given = [s for s in scores if s is not None]
    if not given:
        return None
    avg = round(sum(given) / len(given), 2)
    level = overall_level(avg)
    positive = avg > 4 and 1 not in given
    return ReviewOutcome(
        average=avg,
        level=level,
        result="pozytywna" if positive else "negatywna",
        complete=len(given) == len(scores),
    )
