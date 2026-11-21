"""Funkcje kadrowe z diagramu przypadków użycia KPRM."""

from datetime import date, timedelta


def _emps(client, hr):
    return {e["full_name"]: e for e in client.get("/admin/employees", headers=hr).json()}


def _login(client, email):
    t = client.post("/auth/login", json={"email": email, "password": "demo123"}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_office_structure(client, hr, manager):
    assert client.post("/admin/departments", headers=manager, json={"name": "Wydział Testowy"}).status_code == 403
    d = client.post("/admin/departments", headers=hr, json={"name": "Wydział Kontroli"})
    assert d.status_code == 201
    r = client.patch(f"/admin/departments/{d.json()['id']}", headers=hr, json={"name": "Wydział Kontroli i Audytu"})
    assert r.json()["name"] == "Wydział Kontroli i Audytu"
    listing = client.get("/admin/departments", headers=hr).json()
    cyf = next(x for x in listing if x["name"] == "Wydział Cyfryzacji")
    assert cyf["head"] == "Marek Zieliński" and cyf["employees"] >= 6


def test_substitution_gives_deputy_the_team(client, hr):
    emps = _emps(client, hr)
    marek, ewa = emps["Marek Zieliński"], emps["Ewa Dąbrowska"]
    ewa_h = _login(client, "ewa.dabrowska@demo.gov.pl")
    anna_id = emps["Anna Kowalska"]["id"]
    assert client.get(f"/employees/{anna_id}", headers=ewa_h).status_code == 403
    today = date.today()
    s = client.post("/admin/substitutions", headers=hr, json={
        "absent_employee_id": marek["id"], "deputy_employee_id": ewa["id"],
        "start": today.isoformat(), "end": (today + timedelta(days=14)).isoformat(), "note": "urlop"})
    assert s.status_code == 201 and s.json()["active"] is True
    # zastępca widzi zespół zastępowanego i powiadomienie
    assert client.get(f"/employees/{anna_id}", headers=ewa_h).status_code == 200
    assert any(t["full_name"] == "Anna Kowalska" for t in client.get("/employees", headers=ewa_h).json())
    assert any("Zastępstwo" in n["subject"] for n in client.get("/notifications", headers=ewa_h).json())
    # koniec zastępstwa = koniec dostępu
    client.delete(f"/admin/substitutions/{s.json()['id']}", headers=hr)
    assert client.get(f"/employees/{anna_id}", headers=ewa_h).status_code == 403


def test_historical_review_drives_deadlines(client, hr, manager):
    struct = client.get("/admin/structure", headers=hr).json()
    zielinski = next(m for m in struct["managers"] if m["full_name"] == "Marek Zieliński")
    e = client.post("/admin/employees", headers=hr, json={
        "full_name": "Hanna Historyczna", "position": "Specjalista", "department_id": struct["departments"][0]["id"],
        "manager_id": zielinski["id"], "employment_start": "2015-01-05", "contract_type": "nieokreslony",
        "email": "hanna.historyczna@demo.gov.pl"}).json()
    cycle = next(c for c in client.get("/cycles", headers=manager).json() if c["status"] == "open")
    rv = client.post("/reviews", headers=manager, json={"employee_id": e["id"], "cycle_id": cycle["id"]}).json()
    # bez historii: 24 mies. od zatrudnienia (2015) - termin dawno minął
    assert rv["deadlines"]["due_date"] < "2018-01-01"
    bad = client.post(f"/admin/employees/{e['id']}/historical-reviews", headers=hr, json={
        "drawn_up": "2025-06-10", "result": "pozytywna", "level": "powyżej oczekiwań", "average": 5.2})
    assert bad.status_code == 422  # średnia 5,2 to „na poziomie oczekiwań” (§ 11 ust. 1 pkt 2)
    h = client.post(f"/admin/employees/{e['id']}/historical-reviews", headers=hr, json={
        "drawn_up": "2025-06-10", "acknowledged_at": "2025-06-12", "result": "negatywna",
        "level": "poniżej oczekiwań", "average": 3.6, "note": "arkusz papierowy, teczka 12/2025"})
    assert h.status_code == 201
    # po ocenie negatywnej: ponowna ocena po upływie 6 mies. od zapoznania (art. 81 ust. 9) - 13.12 to sobota
    assert h.json()["due_dates_changed"][0]["due_date"] == "2025-12-15"
    # termin ponownej oceny jest sztywny - bez zmiany w trybie art. 81 ust. 8
    rv2 = client.get(f"/reviews/{rv['id']}", headers=manager).json()
    assert rv2["deadlines"]["is_repeat_review"] is True and rv2["deadlines"]["can_change_due_date"] is False
    hist = client.get(f"/admin/employees/{e['id']}/reviews", headers=hr).json()
    assert hist[0]["historical"] is True and hist[0]["result"] == "negatywna"


def test_import_with_verification(client, hr):
    csv_text = (
        "imie_nazwisko;stanowisko;komorka;przelozony;arkusz;podstawa_zatrudnienia;data_zatrudnienia;email\n"
        "Irena Importowana;Inspektor;Wydział Cyfryzacji;Marek Zieliński;C;nieokreślony;2026-12-01;irena.imp@demo.gov.pl\n"
        "Bez Komorki;Referent;Wydział Nieistniejący;;C;nieokreślony;;\n"
        "Anna Kowalska;Duplikat;Wydział Cyfryzacji;Marek Zieliński;C;mianowanie;;\n"
        "Tymczasowy Pracownik;Referent;Wydział Cyfryzacji;Marek Zieliński;C;określony;2026-12-01;\n")
    preview = client.post("/admin/import/employees", headers=hr, json={"csv": csv_text, "dry_run": True}).json()
    assert preview["valid"] == 2 and preview["created"] == 0
    errs = {r["full_name"]: r["errors"] for r in preview["rows"]}
    assert errs["Bez Komorki"] and errs["Anna Kowalska"]
    tmp = next(r for r in preview["rows"] if r["full_name"] == "Tymczasowy Pracownik")
    assert any("art. 81 ust. 1" in w for w in tmp["warnings"])
    assert "Irena Importowana" not in _emps(client, hr)  # podgląd niczego nie zapisuje
    done = client.post("/admin/import/employees", headers=hr, json={"csv": csv_text, "dry_run": False}).json()
    assert done["created"] == 2 and "Irena Importowana" in _emps(client, hr)
    assert client.get("/admin/import/template.csv", headers=hr).status_code == 200


def test_exports_for_archive_and_reporting(client, hr, manager):
    assert client.get("/admin/export/reviews.csv", headers=manager).status_code == 403
    r = client.get("/admin/export/reviews.csv", headers=hr)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].lstrip("﻿").startswith("id_oceny;pracownik") and len(lines) > 10
    stats = client.get("/admin/export/statistics", headers=hr).json()
    assert stats["total"]["n"] > 10 and "process" in stats
    assert all(v["hidden"] or v["n"] >= stats["k_anonymity"] for v in stats["departments"].values())


def test_promotion_request_notifies_hr(client, hr, admin_h=None):
    """Art. 89 ust. 1: złożenie wniosku o kolejny stopień -> powiadomienie dyrektora generalnego (rola hr)."""
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Employee, Review

    adm = _login(client, "marek.zielinski@demo.gov.pl")  # oceniający (przełożony) - administrator nie ocenia
    with Session(engine) as s:
        emp = s.exec(select(Employee).where(Employee.full_name == "Magdalena Kamińska")).one()
        r = s.exec(select(Review).where(Review.employee_id == emp.id, Review.status.in_(
            ["observation", "draft", "criteria"]))).first()
        rid, crits = r.id, None
    client.post(f"/reviews/{rid}/start", headers=adm)
    rev = client.get(f"/reviews/{rid}", headers=adm).json()
    crits = [{"criterion_id": c["criterion_id"], "score": 9, "justification": "Konkretne osiągnięcia z okresu oceny."}
             for c in rev["criteria"]]
    client.patch(f"/reviews/{rid}", headers=adm, json={
        "criteria": crits, "justification": "Bardzo dobre wyniki.", "ipr_conclusions": "Rozwój w analityce.",
        "promotion_request": "tak", "civil_grade": 3, "promotion_justification": "Wybitne wyniki w okresie oceny."})
    client.post(f"/reviews/{rid}/submit", headers=adm)
    # etap IV: zaproszenie (.ics) i potwierdzenie terminu rozmowy przez ocenianego (§ 10)
    magda = _login(client, "magdalena.kaminska@demo.gov.pl")
    assert client.get(f"/reviews/{rid}/invite.ics?kind=assessment&when=2026-12-05T10:00", headers=adm).status_code == 200
    assert client.post(f"/reviews/{rid}/assessment/confirm", headers=magda).status_code == 200
    client.post(f"/reviews/{rid}/discussed", headers=adm, json={"conversation_date": date.today().isoformat()})
    fin = client.post(f"/reviews/{rid}/finalize", headers=adm)
    assert fin.status_code == 200, fin.text
    assert any("kolejnego stopnia" in n["subject"] for n in client.get("/notifications", headers=hr).json())
