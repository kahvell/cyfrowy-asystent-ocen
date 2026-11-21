"""Przypadki użycia KPRM bez wcześniejszego pokrycia testem: fikcja zapoznania, odrzucenie wniosku o termin,
scheduler (codzienne przypomnienia), ponowne sporządzenie oceny po sprzeciwie, powiadomienia o stopniu."""

from datetime import date, timedelta

from sqlmodel import Session, select

from app.db import engine
from app.models import Notification, Review, User
from app.services import deadlines as dl
from app.services.notify import daily_digest


def _team(client, h):
    return {e["full_name"]: e for e in client.get("/employees", headers=h).json()}


def _login(client, email):
    t = client.post("/auth/login", json={"email": email, "password": "demo123"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def _confirm_assessment_term(client, manager, employee, rid, when="2026-12-05T10:00"):
    """Bramka etapu IV: zaproszenie (.ics) i potwierdzenie terminu rozmowy przez ocenianego (§ 10)."""
    assert client.get(f"/reviews/{rid}/invite.ics?kind=assessment&when={when}", headers=manager).status_code == 200
    assert client.post(f"/reviews/{rid}/assessment/confirm", headers=employee).status_code == 200


def _make_final(client, manager, employee, rid, ipr="Rozwój kompetencji cyfrowych."):
    client.post(f"/reviews/{rid}/start", headers=manager)
    rev = client.get(f"/reviews/{rid}", headers=manager).json()
    crits = [{"criterion_id": c["criterion_id"], "score": c["score"] or 5,
              "justification": c["justification"] or "Konkretne zachowania z okresu oceny."} for c in rev["criteria"]]
    assert client.patch(f"/reviews/{rid}", headers=manager, json={"criteria": crits, "ipr_conclusions": ipr}).status_code == 200
    assert client.post(f"/reviews/{rid}/submit", headers=manager).status_code == 200
    _confirm_assessment_term(client, manager, employee, rid)
    assert client.post(f"/reviews/{rid}/discussed", headers=manager,
                       json={"conversation_date": date.today().isoformat()}).status_code == 200
    fin = client.post(f"/reviews/{rid}/finalize", headers=manager)
    assert fin.status_code == 200, fin.text
    return fin.json()


def test_ack_fiction(client, manager, hr):
    """„Stwierdzenie fikcji zapoznania z oceną” - oceniany nie mógł lub nie chciał potwierdzić."""
    rid = _team(client, manager)["Tomasz Wójcik"]["current_review"]["id"]
    final = _make_final(client, manager, _login(client, "tomasz.wojcik@demo.gov.pl"), rid)
    assert final["status"] == "final"
    assert client.post(f"/reviews/{rid}/ack-fiction", headers=manager, json={"note": "x"}).status_code == 422
    r = client.post(f"/reviews/{rid}/ack-fiction", headers=manager,
                    json={"note": "Informację o ocenie doręczono przez EZD 21.11; oceniany odmówił podpisu."})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "acknowledged" and body["ack_fiction"] is True
    assert body["deadlines"]["objection_deadline"]  # termin na sprzeciw biegnie od doręczenia
    # „koniec cyklu oceny i początek następnego”
    mine = client.get(f"/reviews?employee_id={final['employee']['id']}", headers=manager).json()
    assert any(x["status"] == "criteria" for x in mine)


def _employee_with_login(client, hr, name, **extra):
    """Pracownik z kontem i znanym hasłem (do testów ścieżek ocenianego)."""
    from app.security import hash_password

    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    email = name.lower().replace(" ", ".").replace("ł", "l") + "@demo.gov.pl"
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": name, "position": "Specjalista", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "email": email, **extra}).json()
    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).one()
        u.password_hash = hash_password("demo123")
        s.add(u)
        s.commit()
    t = client.post("/auth/login", json={"email": email, "password": "demo123"}).json()["access_token"]
    return e, {"Authorization": f"Bearer {t}"}


def test_due_date_request_rejected(client, manager, hr):
    """Wniosek ocenianego o zmianę terminu - odrzucenie: powiadomienie, termin bez zmian."""
    e, h = _employee_with_login(client, hr, "Wiktor Wnioskujacy", employment_start="2024-01-02")
    rid = e["review_started"]
    client.patch(f"/reviews/{rid}", headers=manager, json={"opening_conversation_date": "2024-01-10"})
    assert client.post(f"/reviews/{rid}/criteria/confirm", headers=manager).status_code == 200
    assert client.post(f"/reviews/{rid}/criteria/acknowledge", headers=h).json()["status"] == "observation"
    before = client.get(f"/reviews/{rid}", headers=manager).json()["deadlines"]["due_date"]
    req = client.post(f"/reviews/{rid}/due-date-requests", headers=h,
                      json={"proposed_date": "2027-03-01", "reason": "Planowany urlop rodzicielski"})
    assert req.status_code == 201, req.text
    d = client.post(f"/due-date-requests/{req.json()['id']}/decision", headers=manager,
                    json={"accept": False, "note": "Brak podstaw"})
    assert d.status_code == 200 and d.json()["deadlines"]["due_date"] == before
    assert any("Rozpatrzono wniosek" in n["subject"] for n in client.get("/notifications", headers=h).json())
    assert client.get(f"/reviews/{rid}/due-date-requests", headers=h).json()[0]["status"] == "rejected"


def test_scheduler_daily_digest(client):
    """„(scheduler) przypomnienie o wyznaczeniu kryteriów / o zbliżającym się terminie oceny”."""
    with Session(engine) as s:
        before = len(s.exec(select(Notification)).all())
        sent = daily_digest(s)
        after = len(s.exec(select(Notification)).all())
    assert sent > 0 and after - before == sent


def test_objection_second_drawing_up_returns_to_assessment(client, manager, hr):
    """„Ponowne sporządzenie oceny w rezultacie uznania odwołania” - powiadomienie, anulowanie oceny
    i powrót do etapu „rozmowa oceniająca i dokonanie oceny”."""
    e, h = _employee_with_login(client, hr, "Olaf Odwolujacy", employment_start="2024-11-25")
    rid = e["review_started"]
    for st in (client.patch(f"/reviews/{rid}", headers=manager, json={"opening_conversation_date": "2024-12-02"}),
               client.post(f"/reviews/{rid}/criteria/confirm", headers=manager),
               client.post(f"/reviews/{rid}/criteria/acknowledge", headers=h)):
        assert st.status_code == 200, st.text
    _make_final(client, manager, h, rid)
    assert client.post(f"/reviews/{rid}/acknowledge", headers=h).status_code == 200
    ob = client.post(f"/reviews/{rid}/objection", headers=h, json={"text": "Ocena nie uwzględnia moich osiągnięć."})
    assert ob.status_code == 200, ob.text
    r = client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={"decision": "ponowne_sporzadzenie"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "draft" and body["attempt"] == 2
    assert body["reviewer_signed_at"] is None and body["acknowledged_at"] is None
    assert any("Rozpatrzono sprzeciw" in n["subject"] for n in client.get("/notifications", headers=h).json())
    # po sporządzeniu po raz drugi - ponownie zapoznanie i prawo do sprzeciwu (art. 83 ust. 4)
    client.post(f"/reviews/{rid}/submit", headers=manager)
    _confirm_assessment_term(client, manager, h, rid)
    client.post(f"/reviews/{rid}/discussed", headers=manager, json={"conversation_date": date.today().isoformat()})
    assert client.post(f"/reviews/{rid}/finalize", headers=manager).status_code == 200
    again = client.post(f"/reviews/{rid}/acknowledge", headers=h).json()
    assert again["deadlines"]["objection_open"] is True


def test_promotion_application_notifies_employee_and_hr(client, manager, hr):
    """Art. 89 ust. 1 / schemat procesu: złożenie wniosku o kolejny stopień -> powiadomienie kadr (DG)
    i ocenianego („otrzymuje powiadomienie o złożeniu wniosku”)."""
    e, h = _employee_with_login(client, hr, "Urszula Urzedniczka", employment_start="2019-01-02",
                                contract_type="mianowanie", is_civil_servant=True, civil_grade=2,
                                civil_grade_date="2019-06-01")
    rid = e["review_started"]
    steps = [
        client.patch(f"/reviews/{rid}", headers=manager, json={"opening_conversation_date": "2026-11-20"}),
        client.post(f"/reviews/{rid}/criteria/confirm", headers=manager),
        client.post(f"/reviews/{rid}/criteria/acknowledge", headers=h),
        client.post(f"/reviews/{rid}/start", headers=manager),
    ]
    for st in steps:
        assert st.status_code == 200, st.text
    rev = client.get(f"/reviews/{rid}", headers=manager).json()
    crits = [{"criterion_id": c["criterion_id"], "score": 9, "justification": "Wybitne wyniki."} for c in rev["criteria"]]
    for body in ({"criteria": crits, "ipr_conclusions": "Rozwój ekspercki."},
                 {"promotion_request": "tak", "civil_grade": 2,
                  "promotion_justification": "Wyniki znacznie powyżej oczekiwań."}):
        st = client.patch(f"/reviews/{rid}", headers=manager, json=body)
        assert st.status_code == 200, st.text
    assert client.post(f"/reviews/{rid}/submit", headers=manager).status_code == 200
    _confirm_assessment_term(client, manager, h, rid)
    assert client.post(f"/reviews/{rid}/discussed", headers=manager,
                       json={"conversation_date": date.today().isoformat()}).status_code == 200
    fin = client.post(f"/reviews/{rid}/finalize", headers=manager)
    assert fin.status_code == 200, fin.text
    assert fin.json()["promotion_target"] == "trzeciego"
    assert any("kolejnego stopnia" in n["subject"] for n in client.get("/notifications", headers=h).json())
    assert any("kolejnego stopnia" in n["subject"] for n in client.get("/notifications", headers=hr).json())


def test_objection_directly_from_acknowledgement_stage(client, manager, hr):
    """Na etapie zapoznania („nie akceptuję”) oceniany może wnieść sprzeciw bez wcześniejszego potwierdzania
    zapoznania - wniesienie sprzeciwu jest równoznaczne z zapoznaniem się z oceną (art. 83 ust. 1)."""
    e, h = _employee_with_login(client, hr, "Norbert Nieakceptujacy", employment_start="2024-11-25")
    rid = e["review_started"]
    for st in (client.patch(f"/reviews/{rid}", headers=manager, json={"opening_conversation_date": "2024-12-02"}),
               client.post(f"/reviews/{rid}/criteria/confirm", headers=manager),
               client.post(f"/reviews/{rid}/criteria/acknowledge", headers=h)):
        assert st.status_code == 200, st.text
    final = _make_final(client, manager, h, rid)
    # przed zapoznaniem zegar 7 dni nie rusza
    assert final["status"] == "final"
    assert final["acknowledged_at"] is None
    assert final["deadlines"]["objection_deadline"] is None
    assert final["deadlines"]["objection_open"] is False

    obj = client.post(f"/reviews/{rid}/objection", headers=h,
                      json={"text": "Nie akceptuję oceny - nie zgadzam się z oceną kryterium komunikacji."})
    assert obj.status_code == 200, obj.text
    body = obj.json()
    assert body["status"] == "objection"
    assert body["acknowledged_at"] == date.today().isoformat()  # sprzeciw uruchamia zapoznanie
    assert body["objection_at"] == date.today().isoformat()
    # informacja do komórki kadrowej (dyrektor generalny) - 14 dni na rozpatrzenie (art. 83 ust. 3)
    assert any("Sprzeciw od oceny okresowej" in n["subject"] for n in client.get("/notifications", headers=hr).json())
    assert client.post(f"/reviews/{rid}/objection/decision", headers=hr, json={"decision": "odrzucony"}).status_code == 200


def test_objection_window_runs_from_acknowledgement(client, manager, hr):
    """Termin 7 dni biegnie od rzeczywistego zapoznania, po nim biegnie nieprzerwanie (nieobecność go nie
    wstrzymuje ani nie wydłuża), a koniec w dzień wolny przesuwa się na najbliższy dzień roboczy (art. 83 ust. 1)."""
    e, h = _employee_with_login(client, hr, "Beata Bezokienna", employment_start="2024-11-25")
    rid = e["review_started"]
    for st in (client.patch(f"/reviews/{rid}", headers=manager, json={"opening_conversation_date": "2024-12-02"}),
               client.post(f"/reviews/{rid}/criteria/confirm", headers=manager),
               client.post(f"/reviews/{rid}/criteria/acknowledge", headers=h)):
        assert st.status_code == 200, st.text
    _make_final(client, manager, h, rid)
    ack = client.post(f"/reviews/{rid}/acknowledge", headers=h).json()
    assert ack["deadlines"]["objection_open"] is True
    # koniec terminu: 7 dni od zapoznania, przesunięty na dzień roboczy
    assert ack["deadlines"]["objection_deadline"] == dl.days_deadline(date.today(), 7).isoformat()

    # nieobecność (np. L4) po zapoznaniu nie wstrzymuje ani nie wydłuża terminu na sprzeciw
    client.post(f"/admin/employees/{e['id']}/absences", headers=hr, json={
        "start": date.today().isoformat(), "end": (date.today() + timedelta(days=40)).isoformat(),
        "kind": "zwolnienie lekarskie"})
    after = client.get(f"/reviews/{rid}", headers=manager).json()
    assert after["deadlines"]["objection_deadline"] == ack["deadlines"]["objection_deadline"]

    # po upływie 7 dni sprzeciw jest odrzucany
    with Session(engine) as s:
        r = s.get(Review, rid)
        r.acknowledged_at = date.today() - timedelta(days=10)
        s.add(r)
        s.commit()
    late = client.post(f"/reviews/{rid}/objection", headers=h,
                       json={"text": "Sprzeciw po terminie, powinien zostać odrzucony."})
    assert late.status_code == 409
