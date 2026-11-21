"""Proces oceny okresowej wg przypadków użycia KPRM: kryteria -> obserwacja -> ocena -> zapoznanie -> sprzeciw."""

from datetime import date

import pytest


def _team(client, h):
    return {e["full_name"]: e for e in client.get("/employees", headers=h).json()}


def _review_of(client, h, name):
    team = _team(client, h)
    return team[name]["current_review"]["id"]


def test_stage_one_criteria_and_confirmations(client, manager):
    rid = _review_of(client, manager, "Jakub Lewandowski")
    r = client.get(f"/reviews/{rid}", headers=manager).json()
    assert r["status"] == "criteria"
    # nowa umowa od 2.11.2026: kryteria w 30 dni -> 2.12.2026, ocena po 24 miesiącach (2.11.2028 to czwartek)
    assert r["deadlines"]["criteria_deadline"] == "2026-12-02"
    assert r["deadlines"]["due_date"] == "2028-11-02"
    assert r["office"]["city"] and r["employee_form"]["last_name"] == "Lewandowski"

    # na etapie kryteriów nie można wystawiać ocen cząstkowych
    cid = r["criteria"][0]["criterion_id"]
    blocked = client.patch(f"/reviews/{rid}", headers=manager, json={"criteria": [{"criterion_id": cid, "score": 5}]})
    assert blocked.status_code == 409

    # bez daty rozmowy rozpoczynającej nie da się potwierdzić
    assert client.post(f"/reviews/{rid}/criteria/confirm", headers=manager).status_code == 409
    crit = client.get("/criteria", headers=manager).json()
    extra = [c["id"] for c in crit if "C" not in c["mandatory_for"]][:3]
    ok = client.patch(f"/reviews/{rid}", headers=manager, json={
        "additional_criterion_ids": extra, "opening_conversation_date": "2026-11-20",
        "opening_notes": "Omówiono obowiązki, kryteria i oczekiwania."})
    assert ok.status_code == 200, ok.text
    assert sum(c["is_additional"] for c in ok.json()["criteria"]) == 3
    too_many = client.patch(f"/reviews/{rid}", headers=manager, json={"additional_criterion_ids": extra + [crit[-1]["id"]]})
    assert too_many.status_code == 422

    conf = client.post(f"/reviews/{rid}/criteria/confirm", headers=manager, json={"place": "Przykładowo"})
    assert conf.status_code == 200
    assert conf.json()["criteria_reviewer_confirmed_at"] == date.today().isoformat()
    # po potwierdzeniu kryteria są zablokowane
    assert client.patch(f"/reviews/{rid}", headers=manager, json={"additional_criterion_ids": []}).status_code == 409


def test_due_date_extended_by_long_absence(client, manager):
    rid = _review_of(client, manager, "Tomasz Wójcik")
    r = client.get(f"/reviews/{rid}", headers=manager).json()
    assert r["status"] == "observation"
    # 1.12.2024 + 24 mies. = 1.12.2026; nieobecność 1.09-17.10.2025 (47 dni, weekend nie przerywa) -> 17.01.2027 (nd)
    assert r["deadlines"]["due_date"] == "2027-01-18"


def test_due_date_change_requires_reason_and_is_logged(client, manager):
    rid = _review_of(client, manager, "Magdalena Kamińska")
    r = client.post(f"/reviews/{rid}/due-date", headers=manager,
                    json={"due_date": "2027-02-01", "reason": "nieobecnosc_oceniajacego", "note": "urlop"})
    assert r.status_code == 200, r.text
    assert r.json()["deadlines"]["due_date"] == "2027-02-01"
    assert "art. 81 ust. 8" in r.json()["due_date_history"][-1]["reason"]


def test_acknowledgement_objection_and_decision(client, manager, employee, hr):
    rid = _review_of(client, manager, "Anna Kowalska")
    r = client.get(f"/reviews/{rid}", headers=manager).json()
    if r["status"] != "final":
        pytest.skip("wymaga oceny zatwierdzonej w test_api_flow")
    assert r["reviewer_signed_at"] == date.today().isoformat()
    # objaśnienie 7 do arkusza: „okres do” = data sporządzenia oceny na piśmie
    assert r["period_end"] == date.today().isoformat()
    # HR (komórka kadrowa) widzi sporządzony arkusz
    assert client.get(f"/reviews/{rid}", headers=hr).status_code == 200

    ack = client.post(f"/reviews/{rid}/acknowledge", headers=employee, json={"place": "Przykładowo"})
    assert ack.status_code == 200
    body = ack.json()
    assert body["status"] == "acknowledged" and body["deadlines"]["objection_open"] is True

    obj = client.post(f"/reviews/{rid}/objection", headers=employee, json={"text": "Nie zgadzam się z oceną komunikacji."})
    assert obj.status_code == 200 and obj.json()["status"] == "objection"
    # sprzeciw rozpatruje dyrektor generalny, nie oceniający
    assert client.post(f"/reviews/{rid}/objection/decision", headers=manager,
                       json={"decision": "odrzucony"}).status_code == 403
    dec = client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={"decision": "zmiana"})
    assert dec.status_code == 200
    assert dec.json()["status"] == "discussed" and dec.json()["acknowledged_at"] is None


def test_hr_cannot_see_drafts(client, manager, hr):
    rid = _review_of(client, manager, "Piotr Nowak")
    assert client.get(f"/reviews/{rid}", headers=hr).status_code == 403


def test_reminders(client, manager, employee, hr):
    m = client.get("/reminders", headers=manager).json()
    kinds = {x["kind"] for x in m}
    assert "criteria_deadline" in kinds or "employee_confirm_criteria" in kinds
    assert all({"title", "due", "severity", "link"} <= set(x) for x in m)
    assert client.get("/reminders", headers=employee).status_code == 200
    assert client.get("/reminders", headers=hr).status_code == 200


def test_hr_partner_signals_and_access(client, manager, employee, hr):
    team = _team(client, manager)
    kasia = team["Katarzyna Wiśniewska"]["id"]
    r = client.get(f"/employees/{kasia}/hr-partner", headers=manager)
    assert r.status_code == 200
    data = r.json()
    codes = {s["code"] for s in data["signals"]}
    assert "overload" in codes and data["risk"] == "high"
    assert all(s["evidence"] or s["code"] in ("return", "feedback_gap", "no_recognition") for s in data["signals"])
    # magda: świeży sukces -> moment do docenienia
    magda = client.get(f"/employees/{team['Magdalena Kamińska']['id']}/hr-partner", headers=manager).json()
    assert magda["appreciation"]
    # tylko bezpośredni przełożony
    assert client.get(f"/employees/{kasia}/hr-partner", headers=hr).status_code == 403
    assert client.get(f"/employees/{kasia}/hr-partner", headers=employee).status_code == 403
    assert client.get("/team/hr-partner", headers=manager).status_code == 200


def test_conversation_prep(client, manager):
    rid = _review_of(client, manager, "Piotr Nowak")
    for kind in ("opening", "feedback", "assessment"):
        r = client.post(f"/reviews/{rid}/ai/conversation-prep?kind={kind}", headers=manager)
        assert r.status_code == 200, r.text
        p = r.json()["payload"]
        assert p["goal"] and p["agenda"] and len(p["questions"]) >= 3 and p["communication_tips"]


def test_calendar_invite(client, manager):
    rid = _review_of(client, manager, "Piotr Nowak")
    r = client.get(f"/reviews/{rid}/invite.ics?kind=assessment&when=2026-12-01T10:00", headers=manager)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in r.text and "DTSTART:20261201T100000" in r.text


def test_period_from_is_criteria_acknowledgement_date(client, manager):
    """Objaśnienie 6 do arkusza: „okres od” = data zapoznania ocenianego z kryteriami (część I)."""
    rid = _review_of(client, manager, "Tomasz Wójcik")
    before = client.get(f"/reviews/{rid}", headers=manager).json()
    r = client.post(f"/reviews/{rid}/start", headers=manager).json()
    assert r["status"] == "draft"
    assert r["period_start"] == before["criteria_employee_confirmed_at"] == "2024-12-11"
    # termin oceny liczony dalej od początku okresu (24 mies.), nie od daty zapoznania z kryteriami
    assert r["deadlines"]["due_date"] == before["deadlines"]["due_date"]
