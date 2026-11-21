"""Pełny przepływ na danych demo z FakeLLM (bez modelu i bez kluczy API)."""


def _team(client, h):
    return {e["full_name"]: e for e in client.get("/employees", headers=h).json()}


def test_login_rejects_bad_password(client):
    r = client.post("/auth/login", json={"email": "marek.zielinski@demo.gov.pl", "password": "zle"})
    assert r.status_code == 401


def test_access_control(client, manager, other_manager, employee, hr, admin):
    team = _team(client, manager)
    anna = team["Anna Kowalska"]
    # inny kierownik nie widzi cudzych podwładnych
    assert client.get(f"/employees/{anna['id']}/notes", headers=other_manager).status_code == 403
    # HR nie widzi danych indywidualnych, tylko agregaty
    assert client.get("/employees", headers=hr).status_code == 403
    assert client.get(f"/employees/{anna['id']}/notes", headers=hr).status_code == 403
    assert client.get("/analytics/overview", headers=hr).status_code == 200
    assert client.get("/analytics/overview", headers=manager).status_code == 403
    # dashboard urzędu jest tylko dla HR; administrator ma tryb korekty i panel kadrowy
    assert client.get("/analytics/overview", headers=admin).status_code == 403
    # administrator (schemat procesu KPRM: konta + tryb korekty) nie widzi zespołów ani dziennika obserwacji
    assert client.get("/employees?team=all", headers=admin).status_code == 403
    assert client.get(f"/employees/{anna['id']}", headers=admin).status_code == 403
    assert client.get(f"/employees/{anna['id']}/notes", headers=admin).status_code == 403
    # pracownik widzi notatki o sobie (przejrzystość)
    assert client.get(f"/employees/{anna['id']}/notes", headers=employee).status_code == 200


def test_note_is_classified(client, manager):
    team = _team(client, manager)
    jakub = team["Jakub Lewandowski"]
    r = client.post(f"/employees/{jakub['id']}/notes?sync=true", headers=manager,
                    json={"text": "Bardzo sprawnie obsłużył awarię drukarek sieciowych i poinformował wszystkich w mailu."})
    assert r.status_code == 201
    notes = client.get(f"/employees/{jakub['id']}/notes", headers=manager).json()
    note = notes[0]
    assert note["classified"] is True
    assert note["sentiment"] == "positive"
    assert note["criteria"], "heurystyka powinna przypisać kryterium"


def test_manager_note_private_until_shared(client, manager, employee):
    anna = _team(client, manager)["Anna Kowalska"]
    created = client.post(f"/employees/{anna['id']}/notes?sync=true", headers=manager,
                          json={"text": "Robocza notatka naczelnika o Annie - domyślnie niejawna."})
    assert created.status_code == 201
    nid = created.json()["id"]
    assert created.json()["shared_with_employee"] is False
    # notatka przełożonego jest domyślnie niejawna - pracownik jej nie widzi
    assert nid not in {n["id"] for n in client.get(f"/employees/{anna['id']}/notes", headers=employee).json()}
    # przełożony widzi ją w swoim dzienniku
    assert nid in {n["id"] for n in client.get(f"/employees/{anna['id']}/notes", headers=manager).json()}
    # pracownik nie może sam udostępnić notatki przełożonego
    assert client.patch(f"/notes/{nid}/share", headers=employee, json={"shared": True}).status_code == 403
    # przełożony udostępnia - pracownik widzi notatkę
    shared = client.patch(f"/notes/{nid}/share", headers=manager, json={"shared": True})
    assert shared.status_code == 200 and shared.json()["shared_with_employee"] is True
    assert nid in {n["id"] for n in client.get(f"/employees/{anna['id']}/notes", headers=employee).json()}
    # przełożony może cofnąć udostępnienie
    assert client.patch(f"/notes/{nid}/share", headers=manager, json={"shared": False}).status_code == 200
    assert nid not in {n["id"] for n in client.get(f"/employees/{anna['id']}/notes", headers=employee).json()}
    # notatkę własną pracownika można tylko usunąć/współdzielić po stronie "self" - nie udostępnia się jej
    own = client.post(f"/employees/{anna['id']}/notes", headers=employee, json={"text": "Moje osiągnięcie."}).json()
    assert client.patch(f"/notes/{own['id']}/share", headers=manager, json={"shared": True}).status_code == 422


def test_draft_justification_traceable_and_human_decides(client, manager):
    review_id = _team(client, manager)["Anna Kowalska"]["current_review"]["id"]
    review = client.get(f"/reviews/{review_id}", headers=manager).json()
    crit = next(c for c in review["criteria"] if c["code"] == "RZETELNOSC")
    s = client.post(f"/reviews/{review_id}/ai/draft?criterion_id={crit['criterion_id']}", headers=manager).json()
    assert s["status"] == "pending"
    evidence_ids = {n["id"] for n in client.get(f"/reviews/{review_id}/evidence", headers=manager).json()}
    assert s["payload"]["sentences"]
    for sent in s["payload"]["sentences"]:
        assert sent["source_note_ids"], "każde zdanie musi mieć źródło"
        assert set(sent["source_note_ids"]) <= evidence_ids
    # AI nie wystawia oceny
    after = client.get(f"/reviews/{review_id}", headers=manager).json()
    assert next(c for c in after["criteria"] if c["code"] == "RZETELNOSC")["score"] is None
    d = client.post(f"/ai-suggestions/{s['id']}/decision", headers=manager,
                    json={"status": "edited", "final_text": "Poprawiony przez człowieka tekst."}).json()
    assert d["status"] == "edited"
    after = client.get(f"/reviews/{review_id}", headers=manager).json()
    rc = next(c for c in after["criteria"] if c["code"] == "RZETELNOSC")
    assert rc["justification"] == "Poprawiony przez człowieka tekst."
    assert rc["score"] is None
    # decyzja jest jednorazowa
    assert client.post(f"/ai-suggestions/{s['id']}/decision", headers=manager,
                       json={"status": "accepted"}).status_code == 409


def test_quality_check_catches_problems_in_piotr_review(client, manager):
    review_id = _team(client, manager)["Piotr Nowak"]["current_review"]["id"]
    res = client.post(f"/reviews/{review_id}/ai/quality-check", headers=manager).json()
    codes = {w["code"] for w in res["warnings"]}
    assert {"recency", "halo", "vague", "biased_language"} <= codes


def test_full_cycle_with_self_assessment_and_ipr(client, manager, employee, hr):
    review_id = _team(client, manager)["Anna Kowalska"]["current_review"]["id"]
    review = client.get(f"/reviews/{review_id}", headers=manager).json()
    # pracownik nie widzi szkicu ocen przełożonego
    emp_view = client.get(f"/reviews/{review_id}", headers=employee).json()
    assert all(c["score"] is None for c in emp_view["criteria"])

    # nieprawidłowa wartość skali
    bad = client.patch(f"/reviews/{review_id}", headers=manager,
                       json={"criteria": [{"criterion_id": review["criteria"][0]["criterion_id"], "score": 4}]})
    assert bad.status_code == 422

    # niekompletna ocena nie przechodzi do rozmowy
    assert client.post(f"/reviews/{review_id}/submit", headers=manager).status_code == 409

    scores = {"KOMUNIKACJA": 5, "RZETELNOSC": 7, "ORGANIZACJA_PRACY": 9, "WSPOLPRACA": 7, "WIEDZA": 7, "KREATYWNOSC": 7}
    patch = {"criteria": [{"criterion_id": c["criterion_id"], "score": scores[c["code"]]} for c in review["criteria"]]}
    r = client.patch(f"/reviews/{review_id}", headers=manager, json=patch).json()
    assert r["summary"]["result"] == "pozytywna"
    assert r["summary"]["level"] == "powyżej oczekiwań"

    cmp = client.post(f"/reviews/{review_id}/ai/compare-self", headers=manager).json()
    kom = next(x for x in cmp["payload"]["rows"] if x["code"] == "KOMUNIKACJA")
    assert kom["level"] == "major" and cmp["payload"]["questions"]

    assert client.post(f"/reviews/{review_id}/submit", headers=manager).status_code == 200
    # etap IV („Rozmowa oceniająca”): zaproszenie (.ics) i potwierdzenie terminu przez ocenianego (§ 10)
    assert client.get(f"/reviews/{review_id}/invite.ics?kind=assessment&when=2026-11-18T10:00",
                      headers=manager).status_code == 200
    assert client.post(f"/reviews/{review_id}/assessment/confirm", headers=employee).status_code == 200
    assert client.post(f"/reviews/{review_id}/discussed", headers=manager,
                       json={"conversation_date": "2026-11-18"}).status_code == 200
    # bez IPR nie można zatwierdzić (§ 11 ust. 1 pkt 5)
    assert client.post(f"/reviews/{review_id}/finalize", headers=manager).status_code == 409

    ipr = client.post(f"/reviews/{review_id}/ipr/generate", headers=manager).json()
    assert ipr["goals"]
    assert any(g["criterion_name"] == "Komunikacja" for g in ipr["goals"])
    assert client.get(f"/ipr/{ipr['id']}", headers=employee).status_code == 403  # przed ustaleniem
    ok = client.patch(f"/ipr/{ipr['id']}", headers=manager, json={"status": "established"}).json()
    # art. 108 ust. 2: przełożony (naczelnik) jest kierującym komórką -> ustalenie + akceptacja
    assert ok["status"] == "accepted"
    assert client.get(f"/ipr/{ipr['id']}", headers=employee).status_code == 200
    # ustalonego programu nie edytuje się
    assert client.patch(f"/ipr/{ipr['id']}", headers=manager, json={"summary": "x"}).status_code == 409

    # zatwierdzenie przez dyrektora generalnego (rola hr), nie przez przełożonego
    assert client.post(f"/ipr/{ipr['id']}/approve", headers=manager).status_code == 403
    assert any(i["id"] == ipr["id"] for i in client.get("/ipr", headers=hr).json())
    appr = client.post(f"/ipr/{ipr['id']}/approve", headers=hr)
    assert appr.status_code == 200 and appr.json()["status"] == "approved"

    final = client.post(f"/reviews/{review_id}/finalize", headers=manager)
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "final"
    assert final.json()["ipr_conclusions"]


def test_dashboard_k_anonymity_and_calibration(client, hr):
    data = client.get("/analytics/overview", headers=hr).json()
    assert data["distribution"]["departments"]
    flags = {r["reviewer_name"]: r["flag"] for r in data["reviewer_calibration"]}
    assert flags["Ewa Dąbrowska"] == "łagodny"
    for d in data["distribution"]["departments"]:
        if d["n"] < data["distribution"]["k"]:
            assert all(v is None for v in d["levels"].values())


def test_legal_qa_cites_regulation(client, manager):
    r = client.post("/assistant/legal-qa", headers=manager,
                    json={"question": "Czy muszę pisać uzasadnienie oceny negatywnej?"}).json()
    refs = [c["ref"] for c in r["citations"]]
    assert any("§ 11" in ref for ref in refs), refs


def test_review_form_pdf(client, manager, other_manager, employee):
    review_id = _team(client, manager)["Anna Kowalska"]["current_review"]["id"]
    r = client.get(f"/reviews/{review_id}/form.pdf", headers=manager)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
    # dostęp tylko dla uprawnionych do oceny
    assert client.get(f"/reviews/{review_id}/form.pdf", headers=other_manager).status_code == 403
    assert client.get(f"/reviews/{review_id}/form.pdf", headers=employee).status_code == 200


def test_dashboard_date_range_filter(client, hr):
    # domyślnie statystyki obejmują najnowszy zamknięty cykl z ocenami
    base = client.get("/analytics/overview", headers=hr).json()
    assert base["distribution"]["total"]["n"] > 0
    # zakres dat obejmujący okres poprzedniego cyklu (2022-12-01 - 2024-11-30)
    prev = client.get("/analytics/overview?date_from=2022-12-01&date_to=2024-11-30", headers=hr).json()
    assert prev["distribution"]["total"]["n"] == base["distribution"]["total"]["n"]
    # zakres bez sporządzonych ocen - pusty rozkład
    empty = client.get("/analytics/overview?date_from=2000-01-01&date_to=2000-12-31", headers=hr).json()
    assert empty["distribution"]["total"]["n"] == 0
    assert empty["distribution"]["departments"] == []
    # poszczególne endpointy też przyjmują zakres dat
    distrib = client.get("/analytics/distribution?date_from=2000-01-01&date_to=2000-12-31", headers=hr).json()
    assert distrib["total"]["n"] == 0


def test_team_stats_access_filtering_and_range(client, manager, other_manager, employee, hr, admin):
    # dostęp ma tylko przełożony; HR, administrator i pracownik - nie
    assert client.get("/analytics/team", headers=manager).status_code == 200
    assert client.get("/analytics/team", headers=admin).status_code == 403
    assert client.get("/analytics/team", headers=hr).status_code == 403
    assert client.get("/analytics/team", headers=employee).status_code == 403

    team = client.get("/employees", headers=manager).json()
    team_names = {e["full_name"] for e in team}
    data = client.get("/analytics/team", headers=manager).json()
    names = {e["full_name"] for e in data["employees"]}
    assert "Anna Kowalska" in names
    # statystyki obejmują wyłącznie podwładnych przełożonego
    assert names <= team_names
    assert data["summary"]["n_reviews"] >= len(names)
    # pełne dane zespołu - bez progu k-anonimowości (małe grupy nie są ukrywane)
    assert data["summary"]["average"] is not None
    assert all(e["average"] is not None for e in data["employees"])

    # wybór tylko niektórych podwładnych
    anna_id = next(m["id"] for m in team if m["full_name"] == "Anna Kowalska")
    subset = client.get(f"/analytics/team?employee_ids={anna_id}", headers=manager).json()
    assert {e["full_name"] for e in subset["employees"]} == {"Anna Kowalska"}
    assert subset["summary"]["n_reviews"] < data["summary"]["n_reviews"]

    # przełożony nie może wybrać pracownika spoza swojego zespołu
    foreign_id = client.get("/employees", headers=other_manager).json()[0]["id"]
    assert client.get(f"/analytics/team?employee_ids={foreign_id}", headers=manager).json()["employees"] == []

    # zakres dat bez sporządzonych ocen
    empty = client.get("/analytics/team?date_from=2000-01-01&date_to=2000-12-31", headers=manager).json()
    assert empty["employees"] == []
