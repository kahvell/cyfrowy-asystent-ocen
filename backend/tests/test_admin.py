"""Panel kadrowy, wnioski o zmianę terminu, powiadomienia, tryb korekty administratora."""

import pytest


def _admin_emps(client, h):
    return {e["full_name"]: e for e in client.get("/admin/employees", headers=h).json()}


@pytest.fixture(scope="module")
def admin(client):
    r = client.post("/auth/login", json={"email": "admin@demo.gov.pl", "password": "demo123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_hr_employee_list_search_and_access(client, hr, manager, employee):
    assert client.get("/admin/employees", headers=manager).status_code == 403
    assert client.get("/admin/employees", headers=employee).status_code == 403
    found = client.get("/admin/employees?q=cyfryzacji", headers=hr).json()
    assert found and all("Cyfryzacji" in e["department"] for e in found)
    assert client.get("/admin/structure", headers=hr).json()["managers"]


def test_absence_extends_due_date_and_notifies(client, hr, manager):
    magda = _admin_emps(client, hr)["Magdalena Kamińska"]
    rid = magda["review"]["id"]
    before = client.get(f"/reviews/{rid}", headers=manager).json()["deadlines"]["due_date"]
    # zwolnienie 5-16.10.2026 + urlop od 19.10: weekend nie przerywa -> 33 dni > miesiąc
    client.post(f"/admin/employees/{magda['id']}/absences", headers=hr,
                json={"start": "2026-10-05", "end": "2026-10-16", "kind": "zwolnienie lekarskie"})
    r = client.post(f"/admin/employees/{magda['id']}/absences", headers=hr,
                    json={"start": "2026-10-19", "end": "2026-11-06", "kind": "urlop wypoczynkowy"})
    assert r.status_code == 201
    absences = client.get(f"/admin/employees/{magda['id']}/absences", headers=hr).json()
    assert absences["continuous"][-1]["extends_deadline"] is True
    after = client.get(f"/reviews/{rid}", headers=manager).json()["deadlines"]["due_date"]
    # termin Magdy mógł zostać wcześniej zmieniony ręcznie (art. 81 ust. 8) - wtedy zostaje bez zmian
    hist = client.get(f"/reviews/{rid}", headers=manager).json()["due_date_history"]
    if not any("art. 81 ust. 8" in h["reason"] for h in hist):
        assert after > before


def test_change_of_reviewer_moves_active_review(client, hr):
    emps = _admin_emps(client, hr)
    piotr = emps["Piotr Nowak"]
    other = emps["Andrzej Krawczyk"]  # naczelnik Finansów
    r = client.patch(f"/admin/employees/{piotr['id']}", headers=hr,
                     json={"manager_id": other["id"], "reason": "przeniesienie do Wydziału Finansów"})
    assert r.status_code == 200 and r.json()["reviews_moved"]
    fin = client.post("/auth/login", json={"email": "kierownik.finanse@demo.gov.pl", "password": "demo123"}).json()
    h = {"Authorization": f"Bearer {fin['access_token']}"}
    assert client.get(f"/reviews/{piotr['review']['id']}", headers=h).status_code == 200
    assert any("Przejmujesz" in n["subject"] for n in client.get("/notifications", headers=h).json())
    # przywrócenie
    client.patch(f"/admin/employees/{piotr['id']}", headers=hr, json={"manager_id": piotr["manager_id"]})


def test_create_and_delete_employee(client, hr):
    struct = client.get("/admin/structure", headers=hr).json()
    r = client.post("/admin/employees", headers=hr, json={
        "full_name": "Ewa Testowa", "position": "Referent", "department_id": struct["departments"][0]["id"],
        "manager_id": struct["managers"][0]["id"], "employment_start": "2026-11-16", "email": "ewa.testowa@demo.gov.pl"})
    assert r.status_code == 201 and r.json()["initial_password"]
    assert client.delete(f"/admin/employees/{r.json()['id']}", headers=hr).status_code == 200


def test_terminate_keeps_reviews_deletes_notes(client, hr, manager):
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Olga Odchodząca", "position": "Inspektor", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"]}).json()
    client.post(f"/employees/{e['id']}/notes", headers=manager, json={"text": "Notatka robocza przełożonego."})
    r = client.post(f"/admin/employees/{e['id']}/terminate", headers=hr, json={"employment_end": "2026-11-30"})
    assert r.status_code == 200 and r.json()["notes_deleted"] == 1
    assert "Olga Odchodząca" not in _admin_emps(client, hr)
    assert all(t["full_name"] != "Olga Odchodząca" for t in client.get("/employees", headers=manager).json())
    # usunięcie pracownika ze sporządzonymi ocenami (dokumentacja pracownicza) jest zablokowane
    anna = _admin_emps(client, hr)["Anna Kowalska"]
    assert client.delete(f"/admin/employees/{anna['id']}", headers=hr).status_code == 409


def test_due_date_request_flow(client, manager, employee):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Anna Kowalska"]["current_review"]["id"]
    status = client.get(f"/reviews/{rid}", headers=manager).json()["status"]
    r = client.post(f"/reviews/{rid}/due-date-requests", headers=employee,
                    json={"proposed_date": "2027-01-15", "reason": "Planowany urlop rodzicielski w grudniu"})
    if status not in ("observation", "draft", "submitted"):
        assert r.status_code == 409
        return
    assert r.status_code == 201
    req = r.json()
    assert client.post(f"/due-date-requests/{req['id']}/decision", headers=employee, json={"accept": True}).status_code == 403
    d = client.post(f"/due-date-requests/{req['id']}/decision", headers=manager, json={"accept": True})
    assert d.status_code == 200 and d.json()["deadlines"]["due_date"] == "2027-01-15"


def test_admin_correction_mode(client, manager, admin):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Tomasz Wójcik"]["current_review"]["id"]  # okres oceny: kryteria zablokowane
    assert client.patch(f"/reviews/{rid}", headers=manager, json={"opening_notes": "x"}).status_code == 409
    assert client.patch(f"/reviews/{rid}", headers=admin, json={"opening_notes": "x"}).status_code == 409
    ok = client.patch(f"/reviews/{rid}", headers=admin,
                      json={"opening_notes": "Korekta literówki", "correction_reason": "błąd pisarski w ustaleniach"})
    assert ok.status_code == 200 and ok.json()["opening_notes"] == "Korekta literówki"
    log = client.get(f"/reviews/{rid}/corrections", headers=manager).json()
    assert log and log[0]["reason"] == "błąd pisarski w ustaleniach" and "opening_notes" in log[0]["fields"]


def test_notifications_and_mark_read(client, employee):
    rows = client.get("/notifications", headers=employee).json()
    assert isinstance(rows, list)
    assert client.post("/notifications/read", headers=employee).status_code == 200
    assert all(n["read"] for n in client.get("/notifications", headers=employee).json())
