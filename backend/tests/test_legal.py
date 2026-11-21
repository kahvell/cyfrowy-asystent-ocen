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
        prev = s.exec(select(Review).where(Review.employee_id == emp.id, Review.cycle_id == prev_cycle.id)).first()
        cur = Review(employee_id=emp.id, reviewer_id=prev.reviewer_id, cycle_id=prev.cycle_id, status="discussed",
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
    r = client.post("/reviews", headers=admin, json={"employee_id": heads[0]["id"], "cycle_id": cycle["id"]})
    assert r.status_code == 201, r.text
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
