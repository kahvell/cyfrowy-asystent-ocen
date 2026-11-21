"""Proces oceny okresowej wg przypadków użycia KPRM: kryteria -> obserwacja -> ocena -> zapoznanie -> sprzeciw."""

from datetime import date

import pytest

from app.services import deadlines as dl


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
    # 24 mies. od sporządzenia poprzedniej oceny (25.11.2024, art. 81 ust. 4) = 25.11.2026;
    # + nieobecność 1.09-17.10.2025 (47 dni, weekend nie przerywa ciągłości, art. 81 ust. 7) -> 11.01.2027 (pn)
    assert r["deadlines"]["due_date"] == "2027-01-11"


def test_due_date_change_requires_reason_and_is_logged(client, manager):
    rid = _review_of(client, manager, "Magdalena Kamińska")
    r = client.post(f"/reviews/{rid}/due-date", headers=manager,
                    json={"due_date": "2027-02-01", "reason": "nieobecnosc_oceniajacego", "note": "urlop"})
    assert r.status_code == 200, r.text
    assert r.json()["deadlines"]["due_date"] == "2027-02-01"
    assert "art. 81 ust. 8" in r.json()["due_date_history"][-1]["reason"]


def test_acknowledgement_objection_and_decision(client, manager, employee, hr):
    anna = _team(client, manager)["Anna Kowalska"]
    mine = client.get(f"/reviews?employee_id={anna['id']}", headers=manager).json()
    finals = [x for x in mine if x["status"] == "final"]
    if not finals:
        pytest.skip("wymaga oceny zatwierdzonej w test_api_flow")
    rid = finals[0]["id"]
    r = client.get(f"/reviews/{rid}", headers=manager).json()
    # schemat procesu: po sporządzeniu oceny - koniec cyklu i początek następnego (kryteria w 30 dni, § 7)
    nxt = [x for x in mine if x["status"] == "criteria"]
    assert nxt, "po sporządzeniu oceny powinien rozpocząć się kolejny cykl"
    nr = client.get(f"/reviews/{nxt[0]['id']}", headers=manager).json()
    assert nr["deadlines"]["criteria_deadline"] == dl.days_deadline(date.today(), 30).isoformat()
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
    # „zmiana” bez wprowadzonych zmian jest odrzucana - zmianę wpisuje dyrektor generalny w formularzu
    assert client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={"decision": "zmiana"}).status_code == 422
    komunikacja = next(c for c in r["criteria"] if c["code"] == "KOMUNIKACJA")
    # uwzględnienie sprzeciwu nie może obniżyć oceny (art. 83 ust. 4, poradnik KPRM rozdz. 7)
    if komunikacja["score"] > 1:
        low = client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={
            "decision": "zmiana", "changes": {"criteria": [{"criterion_id": komunikacja["criterion_id"], "score": 1}]}})
        assert low.status_code == 422 and "obniżyć" in low.text
    assert komunikacja["score"] <= 7
    dec =client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={
        "decision": "zmiana", "changes": {"criteria": [{"criterion_id": komunikacja["criterion_id"], "score": 7,
                                                        "justification": "Zmieniono po uwzględnieniu sprzeciwu."}]}})
    assert dec.status_code == 200, dec.text
    body = dec.json()
    assert body["status"] == "acknowledged" and body["objection_decision"] == "zmiana"
    assert next(c for c in body["criteria"] if c["code"] == "KOMUNIKACJA")["score"] == 7
    notes = client.get("/notifications", headers=employee).json()
    assert any("zmieniona po sprzeciwie" in n["subject"] for n in notes)


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


def test_new_employee_starts_review_cycle(client, hr, manager):
    """Schemat procesu: „wprowadza dane pracownika podlegającego ocenie” -> przypomnienie o kryteriach
    dla oceniającego i informacja o rozpoczęciu cyklu dla ocenianego."""
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    r = client.post("/admin/employees", headers=hr, json={
        "full_name": "Celina Cyklowa", "position": "Inspektor", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "employment_start": date.today().isoformat(), "email": "celina.c@demo.gov.pl"})
    assert r.status_code == 201 and r.json()["review_started"]
    rv = client.get(f"/reviews/{r.json()['review_started']}", headers=manager).json()
    assert rv["status"] == "criteria"
    assert rv["deadlines"]["criteria_deadline"] == dl.days_deadline(date.today(), 30).isoformat()
    assert any("Wyznacz kryteria" in n["subject"] and "Celina" in n["subject"]
               for n in client.get("/notifications", headers=manager).json())


def test_invitation_notifies_employee(client, manager, employee):
    anna = _team(client, manager)["Anna Kowalska"]
    rid = anna["current_review"]["id"]
    r = client.get(f"/reviews/{rid}/invite.ics?kind=opening&when=2026-12-03T10:00", headers=manager)
    assert r.status_code == 200
    assert any("zaproszenie" in n["subject"] for n in client.get("/notifications", headers=employee).json())
