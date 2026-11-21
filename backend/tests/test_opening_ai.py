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
