"""Przepisy z pełnej ustawy i Standardów ZZL: art. 52/108, art. 71, art. 81 ust. 6 i § 9, onboarding, wyjście."""

from datetime import date

import pytest
from sqlmodel import Session, select

from app.db import engine
from app.models import Employee, Review, ReviewCycle
from app.services import deadlines as dl
from app.services.process import second_negative_risk


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/auth/login", json={"email": "admin@demo.gov.pl", "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _emps(client, hr):
    return {e["full_name"]: e for e in client.get("/admin/employees", headers=hr).json()}


def test_art71_second_negative_for_civil_servant(client):
    with Session(engine) as s:
        emp = s.exec(select(Employee).where(Employee.is_civil_servant, Employee.manager_id.is_not(None))).first()
        prev_cycle = s.exec(select(ReviewCycle).where(ReviewCycle.status == "closed")).first()
        open_cycle = s.exec(select(ReviewCycle).where(ReviewCycle.status == "open")).first()
        prev = s.exec(select(Review).where(Review.employee_id == emp.id, Review.cycle_id == prev_cycle.id)).first()
        cur = Review(employee_id=emp.id, reviewer_id=prev.reviewer_id, cycle_id=open_cycle.id, status="discussed",
                     period_start=prev.period_end, period_end=date(2026, 11, 30), result="negatywna")
        old = prev.result
        prev.result = "negatywna"
        assert second_negative_risk(s, cur) is True
        prev.result = "pozytywna"
        assert second_negative_risk(s, cur) is False
        emp.is_civil_servant = False  # pracownik (nie urzędnik) - art. 71 nie dotyczy
        prev.result = "negatywna"
        assert second_negative_risk(s, cur) is False
        prev.result = old
        s.rollback()


def test_senior_position_has_no_ipr(client, hr, admin):
    heads = [e for e in client.get("/admin/employees", headers=hr).json() if e["senior_position"]]
    assert heads, "kierujący wydziałem w urzędzie wojewódzkim to wyższe stanowisko (art. 52 pkt 2)"
    cycle = next(c for c in client.get("/cycles", headers=admin).json() if c["status"] == "open")
    from app.services.cycle import subject_to_review

    with Session(engine) as s:
        assert subject_to_review(s.get(Employee, heads[0]["id"])) is False  # poradnik KPRM rozdz. 3 - bez auto-cyklu
    # ręczne założenie dozwolone (przykładowy arkusz B KPRM: dyrektor departamentu), z ostrzeżeniem
    r = client.post("/reviews", headers=admin, json={"employee_id": heads[0]["id"], "cycle_id": cycle["id"]})
    assert r.status_code == 201, r.text
    assert "wyższe stanowisko" in r.json()["notice"]
    ipr = client.post(f"/reviews/{r.json()['id']}/ipr/generate", headers=admin)
    assert ipr.status_code == 409 and "art. 108" in ipr.text


def test_position_change_within_6_months_reopens_criteria(client, hr, manager):
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Nowy Przenoszony", "position": "Referent", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "employment_start": "2026-11-16"}).json()
    cycle = next(c for c in client.get("/cycles", headers=manager).json() if c["status"] == "open")
    rv = client.post("/reviews", headers=manager, json={"employee_id": e["id"], "cycle_id": cycle["id"]}).json()
    due_before = rv["deadlines"]["due_date"]
    r = client.patch(f"/admin/employees/{e['id']}", headers=hr, json={
        "position": "Inspektor ds. kontroli", "significant_change_date": "2026-11-25", "reason": "powierzenie innego stanowiska"})
    assert r.status_code == 200
    eff = r.json()["position_change"][0]
    assert eff["effect"] == "criteria_reopened"
    after = client.get(f"/reviews/{rv['id']}", headers=manager).json()
    assert after["status"] == "criteria"
    assert after["deadlines"]["criteria_deadline"] == dl.days_deadline(date(2026, 11, 25), 30).isoformat() == "2026-12-28"
    assert after["deadlines"]["due_date"] == due_before  # § 9 ust. 1: termin oceny nie ulega zmianie


def test_position_change_after_6_months_requires_review(client, hr, manager):
    magda = _emps(client, hr)["Magdalena Kamińska"]
    r = client.patch(f"/admin/employees/{magda['id']}", headers=hr, json={
        "position": "Główny specjalista ds. analizy danych", "significant_change_date": "2026-11-23"})
    eff = r.json()["position_change"][0]
    assert eff["effect"] == "review_due"
    assert eff["due_date"] == "2026-12-23"  # 30 dni od zmiany (art. 81 ust. 6, § 9 ust. 2)


def test_onboarding_signal_for_new_employee(client, manager):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    data = client.get(f"/employees/{team['Jakub Lewandowski']['id']}/hr-partner", headers=manager).json()
    onboarding = next(s for s in data["signals"] if s["code"] == "onboarding")
    assert "Standardy ZZL" in onboarding["message"]


def test_exit_review_on_request(client, hr):
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Odchodzący Na Wniosek", "position": "Referent", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"]}).json()
    r = client.post(f"/admin/employees/{e['id']}/terminate", headers=hr,
                    json={"employment_end": "2026-12-31", "review_requested": True})
    assert r.status_code == 200 and r.json()["review_requested"] is True and r.json()["active"] is True


def _scenario(s, *, prev_result, prev_level="powyżej oczekiwań", grade_date=None, ack=date(2024, 11, 27)):
    emp = s.exec(select(Employee).where(Employee.is_civil_servant, Employee.manager_id.is_not(None))).first()
    prev_cycle = s.exec(select(ReviewCycle).where(ReviewCycle.status == "closed")).first()
    open_cycle = s.exec(select(ReviewCycle).where(ReviewCycle.status == "open")).first()
    prev = s.exec(select(Review).where(Review.employee_id == emp.id, Review.cycle_id == prev_cycle.id)).first()
    prev.result, prev.overall_level = prev_result, prev_level
    prev.reviewer_signed_at, prev.acknowledged_at = date(2024, 11, 25), ack
    emp.civil_grade_date = grade_date
    emp.employment_start = date(2019, 3, 1)
    cur = Review(employee_id=emp.id, reviewer_id=prev.reviewer_id, cycle_id=open_cycle.id, status="discussed",
                 period_start=open_cycle.period_start, period_end=open_cycle.period_end)
    return emp, prev, cur


def test_deadlines_count_from_previous_review():
    """Art. 81 ust. 4 i § 7 pkt 1: 24 miesiące i 30 dni liczone od sporządzenia poprzedniej oceny."""
    from app.services.process import deadline_base, init_deadlines

    with Session(engine) as s:
        _, prev, cur = _scenario(s, prev_result="pozytywna")
        assert deadline_base(s, cur) == date(2024, 11, 25)
        init_deadlines(s, cur)
        assert cur.criteria_deadline == date(2024, 12, 27)  # 25.12 i 26.12 to święta
        assert cur.due_date >= date(2026, 11, 25)  # + ewentualne długie nieobecności
        s.rollback()


def test_repeat_review_six_months_after_negative():
    """Art. 81 ust. 9 i § 7 pkt 2: po ocenie negatywnej - kryteria w 7 dni, ocena 6 mies. od zapoznania."""
    from app.services.process import init_deadlines

    with Session(engine) as s:
        _, prev, cur = _scenario(s, prev_result="negatywna", ack=date(2024, 11, 27))
        init_deadlines(s, cur)
        assert cur.criteria_deadline == date(2024, 12, 2)  # 25.11 + 7 = 2.12 (pn)
        assert cur.due_date == date(2025, 5, 28)  # dzień po upływie 6 mies. od 27.11.2024 (śr)
        s.rollback()


def test_repeat_review_date_matches_kprm_guide():
    assert dl.repeat_review_date(date(2025, 2, 15)) == date(2025, 8, 18)  # 16.08.2025 to sobota -> pn 18.08
    assert dl.repeat_review_date(date(2024, 2, 15)) == date(2024, 8, 16)  # przykład z poradnika: 15.02 -> 16.08


def test_obligatory_promotion_counts_from_last_grade():
    """Art. 89 ust. 2: dwie kolejne oceny na najwyższych poziomach OD otrzymania ostatniego stopnia."""
    from app.services.process import obligatory_promotion

    with Session(engine) as s:
        emp, prev, cur = _scenario(s, prev_result="pozytywna", grade_date=date(2022, 12, 20))
        cur.result, cur.overall_level = "pozytywna", "znacznie powyżej oczekiwań"
        emp.civil_grade = 3
        assert obligatory_promotion(s, cur) is True
        emp.civil_grade_date = date(2025, 6, 1)  # stopień przyznany po poprzedniej ocenie -> liczenie od nowa
        assert obligatory_promotion(s, cur) is False
        s.rollback()


def test_fixed_term_contract_not_subject_to_periodic_review(client, hr, manager):
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Na Czas Określony", "position": "Referent", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "contract_type": "okreslony"}).json()
    cycle = next(c for c in client.get("/cycles", headers=manager).json() if c["status"] == "open")
    r = client.post("/reviews", headers=manager, json={"employee_id": e["id"], "cycle_id": cycle["id"]})
    assert r.status_code == 422 and "art. 81 ust. 1" in r.text


def test_form_fields_from_kprm_automated_sheet():
    """Arkusz zautomatyzowany i schemat pól KPRM: stopień „III - trzeci”, „okres do” przy ocenie po terminie."""
    from app.services.process import grade_label

    assert grade_label(3) == "III - trzeci" and grade_label(9) == "IX - dziewiąty" and grade_label(None) is None


def test_late_review_period_end_is_due_date(client, hr, manager):
    """Schemat pól: „okres do” = data sporządzenia, a gdy ocenę sporządza się po terminie - data terminu."""
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Piotr Spozniony", "position": "Specjalista", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "employment_start": "2019-01-02"}).json()
    rid = e["review_started"]
    due = client.get(f"/reviews/{rid}", headers=manager).json()["deadlines"]["due_date"]
    assert due < date.today().isoformat()  # ocena po terminie
    with Session(engine) as s:  # rozmowa i potwierdzenia jak po stronie ocenianego
        r = s.get(Review, rid)
        r.opening_conversation_date = r.criteria_reviewer_confirmed_at = r.criteria_employee_confirmed_at = date(2019, 1, 10)
        r.status = "observation"
        s.add(r)
        s.commit()
    client.post(f"/reviews/{rid}/start", headers=manager)
    rev = client.get(f"/reviews/{rid}", headers=manager).json()
    crits = [{"criterion_id": c["criterion_id"], "score": 5, "justification": "Zgodnie z oczekiwaniami."} for c in rev["criteria"]]
    assert client.patch(f"/reviews/{rid}", headers=manager, json={
        "criteria": crits, "ipr_conclusions": "Rozwój.", "signature_method": "wydruk"}).status_code == 200
    client.post(f"/reviews/{rid}/submit", headers=manager)
    client.post(f"/reviews/{rid}/discussed", headers=manager, json={"conversation_date": date.today().isoformat()})
    fin = client.post(f"/reviews/{rid}/finalize", headers=manager).json()
    assert fin["period_end"] == due and fin["reviewer_signed_at"] == date.today().isoformat()
    assert fin["signature_method"] == "wydruk"
