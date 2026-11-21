"""Statystyki dla HR / dyrektora generalnego - czyste zapytania SQL, bez LLM.

Każdy agregat jest objęty progiem k-anonimowości: grupy mniejsze niż K są ukrywane.
"""

from collections import Counter, defaultdict

from sqlmodel import Session, func, select

from app.config import settings
from app.models import (
    AISuggestion,
    Criterion,
    Department,
    Employee,
    Review,
    ReviewCriterion,
    ReviewCycle,
    User,
)
from app.services.scoring import SCALE

DONE = ("final", "acknowledged", "objection")  # oceny sporządzone

LEVELS = list(SCALE.values())


def default_cycle(session: Session) -> ReviewCycle | None:
    """Najnowszy zamknięty cykl z ocenami; jeśli brak - najnowszy cykl z jakąkolwiek zatwierdzoną oceną.
    (Cykl w toku ma zwykle pojedyncze oceny - jego rozkład byłby mylący.)"""
    base = select(ReviewCycle).join(Review, Review.cycle_id == ReviewCycle.id).where(Review.status.in_(DONE))
    order = ReviewCycle.period_start.desc()
    return session.exec(base.where(ReviewCycle.status == "closed").order_by(order)).first() \
        or session.exec(base.order_by(order)).first()


def _final_reviews(session: Session, cycle_id: int | None):
    q = select(Review, Employee).join(Employee, Employee.id == Review.employee_id).where(Review.status.in_(DONE))
    if cycle_id:
        q = q.where(Review.cycle_id == cycle_id)
    return session.exec(q).all()


def distribution(session: Session, cycle_id: int | None) -> dict:
    k = settings.k_anonymity
    depts = {d.id: d.name for d in session.exec(select(Department)).all()}
    by_dept: dict[int, Counter] = defaultdict(Counter)
    total: Counter = Counter()
    for r, e in _final_reviews(session, cycle_id):
        by_dept[e.department_id][r.overall_level] += 1
        total[r.overall_level] += 1
    rows = []
    for dept_id, cnt in sorted(by_dept.items(), key=lambda x: depts.get(x[0], "")):
        n = sum(cnt.values())
        top_share = (cnt[SCALE[9]] + cnt[SCALE[7]]) / n if n else 0
        rows.append({
            "department": depts.get(dept_id, "?"), "n": n, "hidden": n < k,
            "levels": {lvl: (cnt[lvl] if n >= k else None) for lvl in LEVELS},
            "top_share": round(top_share, 2) if n >= k else None,
            "flag": "inflacja ocen" if n >= k and top_share >= 0.8 else None,
        })
    n_total = sum(total.values())
    return {"k": k, "total": {"n": n_total, "levels": {lvl: total[lvl] for lvl in LEVELS}}, "departments": rows}


def competency_gaps(session: Session, cycle_id: int | None) -> dict:
    k = settings.k_anonymity
    q = (
        select(Criterion.id, Criterion.name, Criterion.code, func.avg(ReviewCriterion.score),
               func.count(ReviewCriterion.id))
        .join(ReviewCriterion, ReviewCriterion.criterion_id == Criterion.id)
        .join(Review, Review.id == ReviewCriterion.review_id)
        .where(Review.status.in_(DONE), ReviewCriterion.score.is_not(None))
        .group_by(Criterion.id, Criterion.name, Criterion.code)
    )
    if cycle_id:
        q = q.where(Review.cycle_id == cycle_id)
    rows = []
    for cid, name, code, avg, n in session.exec(q).all():
        rows.append({"criterion_id": cid, "code": code, "name": name, "n": n,
                     "average": round(float(avg), 2) if n >= k else None, "hidden": n < k})
    rows.sort(key=lambda r: (r["average"] is None, r["average"] or 0))
    return {"k": k, "criteria": rows}


def reviewer_calibration(session: Session, cycle_id: int | None = None) -> list[dict]:
    """Średnia ocen danego oceniającego vs średnia urzędu: łagodność / surowość."""
    k = settings.k_anonymity
    q = select(Review.reviewer_id, func.avg(Review.overall_score), func.count(Review.id)) \
        .where(Review.status.in_(DONE), Review.overall_score.is_not(None)).group_by(Review.reviewer_id)
    office_q = select(func.avg(Review.overall_score)).where(Review.status.in_(DONE))
    if cycle_id:
        q = q.where(Review.cycle_id == cycle_id)
        office_q = office_q.where(Review.cycle_id == cycle_id)
    office_avg = session.exec(office_q).one()
    if office_avg is None:
        return []
    names = {u.id: u.full_name for u in session.exec(select(User)).all()}
    out = []
    for reviewer_id, avg, n in session.exec(q).all():
        delta = float(avg) - float(office_avg)
        flag = None
        if n >= k and delta >= 1.0:
            flag = "łagodny"
        elif n >= k and delta <= -1.0:
            flag = "surowy"
        out.append({"reviewer_id": reviewer_id, "reviewer_name": names.get(reviewer_id), "n": n,
                    "average": round(float(avg), 2) if n >= k else None, "office_average": round(float(office_avg), 2),
                    "delta": round(delta, 2) if n >= k else 0.0, "flag": flag, "hidden": n < k})
    return sorted(out, key=lambda r: -(r["delta"] or 0))


def gender_gap(session: Session, cycle_id: int | None) -> dict:
    """Średni wynik wg płci - wykrywanie systematycznej stronniczości. Tylko grupy >= K."""
    k = settings.k_anonymity
    groups: dict[str, list[float]] = defaultdict(list)
    for r, e in _final_reviews(session, cycle_id):
        if e.gender and r.overall_score is not None:
            groups[e.gender].append(r.overall_score)
    rows = {g: {"n": len(v), "average": round(sum(v) / len(v), 2) if len(v) >= k else None}
            for g, v in groups.items()}
    gap = None
    if all(rows.get(g, {}).get("average") is not None for g in ("K", "M")):
        gap = round(rows["K"]["average"] - rows["M"]["average"], 2)
    return {"k": k, "groups": rows, "gap_k_minus_m": gap}


def ai_adoption(session: Session) -> dict:
    rows = session.exec(
        select(AISuggestion.kind, AISuggestion.status, func.count(AISuggestion.id))
        .where(AISuggestion.kind.in_(["draft_justification", "ipr"]))
        .group_by(AISuggestion.kind, AISuggestion.status)
    ).all()
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"pending": 0, "accepted": 0, "edited": 0, "rejected": 0})
    for kind, status, n in rows:
        out[kind][status] = n
    models = session.exec(select(AISuggestion.model, func.count(AISuggestion.id)).group_by(AISuggestion.model)).all()
    return {"by_kind": dict(out), "by_model": {m: n for m, n in models}}
