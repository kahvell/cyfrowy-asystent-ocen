"""Etap I (§ 5): AI pomaga oceniającemu dobrać kryteria dodatkowe, a ocenianemu przygotować się do rozmowy."""

from tests.conftest import _login


def _criteria_review(client, manager, name="Jakub Lewandowski"):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    r = team[name]["current_review"]
    assert r and r["status"] == "criteria"
    return r["id"]


def test_suggest_criteria_uses_history_and_respects_rules(client, manager):
    rid = _criteria_review(client, manager)
    s = client.post(f"/reviews/{rid}/ai/suggest-criteria", headers=manager)
    assert s.status_code == 200, s.text
    p = s.json()["payload"]
    review = client.get(f"/reviews/{rid}", headers=manager).json()
    mandatory = {c["criterion_id"] for c in review["criteria"] if not c["is_additional"]}
    # § 5 ust. 2: maks. 3 kryteria dodatkowe, bez kryteriów obowiązkowych i bez powtórzeń
    ids = [x["criterion_id"] for x in p["proposals"]]
    assert len(ids) <= 3 and len(set(ids)) == len(ids) and not (set(ids) & mandatory)
    assert p["proposals"], "dane demo zawierają historię - powinna być co najmniej jedna propozycja"
    # każda propozycja wskazuje dane, na których się opiera
    assert all(x["why"] and x["evidence"] for x in p["proposals"])
    # decyzja człowieka trafia do historii propozycji
    d = client.post(f"/ai-suggestions/{s.json()['id']}/decision", headers=manager, json={"status": "accepted"})
    assert d.status_code == 200


def test_suggest_criteria_only_for_reviewer_and_stage_one(client, manager, employee, admin):
    rid = _criteria_review(client, manager)
    assert client.post(f"/reviews/{rid}/ai/suggest-criteria", headers=employee).status_code == 403
    assert client.post(f"/reviews/{rid}/ai/suggest-criteria", headers=admin).status_code == 403
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    later = team["Magdalena Kamińska"]["current_review"]["id"]  # okres oceny - kryteria już ustalone
    assert client.post(f"/reviews/{later}/ai/suggest-criteria", headers=manager).status_code == 409


def test_employee_opening_prep(client, manager):
    rid = _criteria_review(client, manager)
    jakub = _login(client, "jakub.lewandowski@demo.gov.pl")
    r = client.post(f"/reviews/{rid}/ai/employee-opening-prep", headers=jakub)
    assert r.status_code == 200, r.text
    p = r.json()["payload"]
    review = client.get(f"/reviews/{rid}", headers=jakub).json()
    assert len(p["criteria_guide"]) == len(review["criteria"])
    assert p["agree_disagree"] and p["my_goals"] and p["questions"]
    # przełożony nie generuje tego za pracownika i nie widzi go na liście propozycji AI
    assert client.post(f"/reviews/{rid}/ai/employee-opening-prep", headers=manager).status_code == 403
    kinds = {s["kind"] for s in client.get(f"/reviews/{rid}/ai-suggestions", headers=manager).json()}
    assert "employee_opening_prep" not in kinds


def test_assessment_prep_gives_feedback_per_criterion(client, manager):
    """Przed rozmową oceniającą: podsumowanie okresu i informacja zwrotna kryterium po kryterium."""
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Piotr Nowak"]["current_review"]["id"]  # przygotowanie oceny (szkic)
    r = client.post(f"/reviews/{rid}/ai/conversation-prep?kind=assessment", headers=manager)
    assert r.status_code == 200, r.text
    p = r.json()["payload"]
    assert p["watch_out"] and p["feedback"] and p["summary"]
    assert {f["kind"] for f in p["feedback"]} <= {"docenienie", "rozwoj", "dopytaj"}
    evidence = {n["id"] for n in client.get(f"/reviews/{rid}/evidence", headers=manager).json()}
    assert all(set(f["source_note_ids"]) <= evidence for f in p["feedback"])


def test_self_assessment_window_is_stage_2_and_3(client, manager):
    """Samoocena powstaje niezależnie od ocen przełożonego: etapy II-III; od etapu IV oceniany widzi już oceny."""

    from sqlmodel import Session

    from app.db import engine
    from app.models import Review

    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Magdalena Kamińska"]["current_review"]["id"]  # okres oceny
    magda = _login(client, "magdalena.kaminska@demo.gov.pl")
    assert client.get(f"/reviews/{rid}/self-assessment", headers=magda).json()["open"] is True
    with Session(engine) as s:
        r = s.get(Review, rid)
        old = r.status
        r.status = "submitted"
        s.add(r)
        s.commit()
    try:
        assert client.get(f"/reviews/{rid}/self-assessment", headers=magda).json()["open"] is False
        put = client.put(f"/reviews/{rid}/self-assessment", headers=magda, json={"items": {}, "summary": "x", "submit": False})
        assert put.status_code == 409
    finally:
        with Session(engine) as s:
            r = s.get(Review, rid)
            r.status = old
            s.add(r)
            s.commit()


def test_development_wheel_shared_with_manager_and_used_in_suggestions(client, manager, employee):
    """Koło rozwoju: oceniany zaznacza teraz/cel, wybiera obszary i proponuje kryterium; przełożony widzi po udostępnieniu."""
    rid = _criteria_review(client, manager)
    jakub = _login(client, "jakub.lewandowski@demo.gov.pl")
    w = client.get(f"/reviews/{rid}/wheel", headers=jakub).json()
    assert w["editable"] and w["criteria"] and w["proposable"]
    cids = [c["criterion_id"] for c in w["criteria"]]
    proposed = w["proposable"][0]["criterion_id"]
    body = {"items": {str(c): {"now": 3, "target": 7} for c in cids}, "focus": cids[:2],
            "proposed_criterion_id": proposed, "note": "Chcę rozwijać się w analizie danych.", "share": False}
    assert client.put(f"/reviews/{rid}/wheel", headers=jakub, json=body).status_code == 200
    # przed udostępnieniem przełożony nie widzi treści; inny pracownik w ogóle
    assert client.get(f"/reviews/{rid}/wheel", headers=manager).json()["shared_at"] is None
    assert client.get(f"/reviews/{rid}/wheel", headers=manager).json()["items"] == {}
    assert client.get(f"/reviews/{rid}/wheel", headers=employee).status_code == 403
    # walidacja: skala 1/3/5/7/9 jak oceny cząstkowe, maks. 2 obszary
    bad = {**body, "items": {str(cids[0]): {"now": 4, "target": 8}}}
    assert client.put(f"/reviews/{rid}/wheel", headers=jakub, json=bad).status_code == 422
    assert client.put(f"/reviews/{rid}/wheel", headers=jakub, json={**body, "focus": cids[:3]}).status_code == 422
    # udostępnienie -> przełożony widzi koło, a propozycja kryteriów uwzględnia wskazanie pracownika
    assert client.put(f"/reviews/{rid}/wheel", headers=jakub, json={**body, "share": True}).json()["shared_at"]
    seen = client.get(f"/reviews/{rid}/wheel", headers=manager).json()
    assert seen["items"] and seen["proposed_criterion_id"] == proposed and not seen["editable"]
    p = client.post(f"/reviews/{rid}/ai/suggest-criteria", headers=manager).json()["payload"]
    assert any(x["criterion_id"] == proposed and any("koło rozwoju" in e for e in x["evidence"])
               for x in p["proposals"])
