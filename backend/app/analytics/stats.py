"""Statystyki dla HR / dyrektora generalnego - czyste zapytania SQL, bez LLM.

Każdy agregat jest objęty progiem k-anonimowości: grupy mniejsze niż K są ukrywane.
"""

from collections import Counter, defaultdict
from datetime import date

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
from app.services.process import drawn_up_date
from app.services.scoring import SCALE

DONE = ("final", "acknowledged", "objection")  # oceny sporządzone

LEVELS = list(SCALE.values())


def _period_filter(q, date_from: date | None, date_to: date | None):
    """Zawęża oceny do tych, których okres oceny (period_start-period_end) mieści się w wybranym zakresie dat."""
    if date_from:
        q = q.where(Review.period_start >= date_from)
    if date_to:
        q = q.where(Review.period_end <= date_to)
    return q


def default_cycle(session: Session) -> ReviewCycle | None:
    """Najnowszy zamknięty cykl z ocenami; jeśli brak - najnowszy cykl z jakąkolwiek zatwierdzoną oceną.
    (Cykl w toku ma zwykle pojedyncze oceny - jego rozkład byłby mylący.)"""
    base = select(ReviewCycle).join(Review, Review.cycle_id == ReviewCycle.id).where(Review.status.in_(DONE))
    order = ReviewCycle.period_start.desc()
    return session.exec(base.where(ReviewCycle.status == "closed").order_by(order)).first() \
        or session.exec(base.order_by(order)).first()


def _final_reviews(session: Session, cycle_id: int | None, date_from: date | None = None,
                   date_to: date | None = None):
    q = select(Review, Employee).join(Employee, Employee.id == Review.employee_id).where(Review.status.in_(DONE))
    if cycle_id:
        q = q.where(Review.cycle_id == cycle_id)
    q = _period_filter(q, date_from, date_to)
    return session.exec(q).all()


def distribution(session: Session, cycle_id: int | None, date_from: date | None = None,
                 date_to: date | None = None) -> dict:
    k = settings.k_anonymity
    depts = {d.id: d.name for d in session.exec(select(Department)).all()}
    by_dept: dict[int, Counter] = defaultdict(Counter)
    total: Counter = Counter()
    for r, e in _final_reviews(session, cycle_id, date_from, date_to):
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


def competency_gaps(session: Session, cycle_id: int | None, date_from: date | None = None,
                    date_to: date | None = None) -> dict:
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
    q = _period_filter(q, date_from, date_to)
    rows = []
    for cid, name, code, avg, n in session.exec(q).all():
        rows.append({"criterion_id": cid, "code": code, "name": name, "n": n,
                     "average": round(float(avg), 2) if n >= k else None, "hidden": n < k})
    rows.sort(key=lambda r: (r["average"] is None, r["average"] or 0))
    return {"k": k, "criteria": rows}


def reviewer_calibration(session: Session, cycle_id: int | None = None, date_from: date | None = None,
                         date_to: date | None = None) -> list[dict]:
    """Średnia ocen danego oceniającego vs średnia urzędu: łagodność / surowość."""
    k = settings.k_anonymity
    q = select(Review.reviewer_id, func.avg(Review.overall_score), func.count(Review.id)) \
        .where(Review.status.in_(DONE), Review.overall_score.is_not(None)).group_by(Review.reviewer_id)
    office_q = select(func.avg(Review.overall_score)).where(Review.status.in_(DONE))
    if cycle_id:
        q = q.where(Review.cycle_id == cycle_id)
        office_q = office_q.where(Review.cycle_id == cycle_id)
    q = _period_filter(q, date_from, date_to)
    office_q = _period_filter(office_q, date_from, date_to)
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


def gender_gap(session: Session, cycle_id: int | None, date_from: date | None = None,
               date_to: date | None = None) -> dict:
    """Średni wynik wg płci - wykrywanie systematycznej stronniczości. Tylko grupy >= K."""
    k = settings.k_anonymity
    groups: dict[str, list[float]] = defaultdict(list)
    for r, e in _final_reviews(session, cycle_id, date_from, date_to):
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


def team_stats(session: Session, employee_ids: set[int], date_from: date | None = None,
               date_to: date | None = None) -> dict:
    """Wyniki ocen podwładnych dla przełożonego (zawężone do wybranych osób i zakresu okresu oceny).

    Bez progu k-anonimowości - przełożony ma i tak dostęp do indywidualnych ocen swoich podwładnych."""
    employees: list[dict] = []
    reviews_flat: list[Review] = []
    review_ids: list[int] = []
    if employee_ids:
        q = (select(Review, Employee, ReviewCycle)
             .join(Employee, Employee.id == Review.employee_id)
             .join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
             .where(Review.employee_id.in_(employee_ids), Review.status.in_(DONE)))
        q = _period_filter(q, date_from, date_to)
        by_emp: dict[int, list[tuple[Review, ReviewCycle]]] = defaultdict(list)
        emp_objs: dict[int, Employee] = {}
        for r, e, c in session.exec(q).all():
            by_emp[e.id].append((r, c))
            emp_objs[e.id] = e
            reviews_flat.append(r)
            review_ids.append(r.id)
        depts = {d.id: d.name for d in session.exec(select(Department)).all()}
        for eid in sorted(by_emp, key=lambda i: emp_objs[i].full_name):
            e = emp_objs[eid]
            items = sorted(by_emp[eid], key=lambda rc: rc[1].period_start, reverse=True)
            rev_list = [{
                "review_id": r.id, "cycle_id": c.id, "cycle": c.name,
                "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
                "score": round(r.overall_score, 2) if r.overall_score is not None else None,
                "level": r.overall_level, "result": r.result, "status": r.status,
                "drawn_up": drawn_up_date(r).isoformat(),
            } for r, c in items]
            scores = [x["score"] for x in rev_list if x["score"] is not None]
            latest = rev_list[0]
            employees.append({
                "employee_id": e.id, "full_name": e.full_name, "position": e.position,
                "department": depts.get(e.department_id), "reviews": rev_list, "n": len(rev_list),
                "average": round(sum(scores) / len(scores), 2) if scores else None,
                "latest_level": latest["level"], "latest_result": latest["result"], "latest_score": latest["score"],
            })
    levels = Counter(r.overall_level for r in reviews_flat if r.overall_level)
    results = Counter(r.result for r in reviews_flat if r.result)
    scores = [r.overall_score for r in reviews_flat if r.overall_score is not None]
    criteria_rows: list[dict] = []
    if review_ids:
        cq = (select(Criterion.code, Criterion.name, func.avg(ReviewCriterion.score), func.count(ReviewCriterion.id))
              .join(ReviewCriterion, ReviewCriterion.criterion_id == Criterion.id)
              .where(ReviewCriterion.review_id.in_(review_ids), ReviewCriterion.score.is_not(None))
              .group_by(Criterion.id, Criterion.code, Criterion.name))
        criteria_rows = sorted(
            ({"code": code, "name": name, "average": round(float(avg), 2), "n": n}
             for code, name, avg, n in session.exec(cq).all()),
            key=lambda x: x["average"])
    return {
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "employees": employees,
        "summary": {
            "n_employees": len(employees), "n_reviews": len(reviews_flat),
            "average": round(sum(scores) / len(scores), 2) if scores else None,
            "levels": {lv: levels[lv] for lv in LEVELS if levels[lv]},
            "results": dict(results), "criteria": criteria_rows,
        },
    }
