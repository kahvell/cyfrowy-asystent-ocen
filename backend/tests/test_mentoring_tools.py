"""Narzędzia mentoringowe: okno Johari (etap IV), 70-20-10 w IPR, SMART w celach IPR."""

from sqlmodel import Session, select

from app.api.opening import johari_quadrant
from app.db import engine
from app.models import Review, SelfAssessment
from tests.conftest import _login


def test_johari_quadrants_rules():
    assert johari_quadrant(9, 7) == "arena"
    assert johari_quadrant(7, 3) == "blind"      # przełożony widzi więcej niż pracownik
    assert johari_quadrant(3, 9) == "facade"     # pracownik widzi więcej niż przełożony
    assert johari_quadrant(5, 5) == "unknown"
    assert johari_quadrant(None, 5) == "unknown"


def test_johari_endpoint_before_assessment_conversation(client, manager):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Piotr Nowak"]["current_review"]["id"]
    assert client.get(f"/reviews/{rid}/johari", headers=manager).status_code == 409  # szkic - za wcześnie
    with Session(engine) as s:
        r = s.get(Review, rid)
        old = r.status
        r.status = "submitted"
        sa = s.exec(select(SelfAssessment).where(SelfAssessment.review_id == rid)).first()
        created = sa is None
        if created:
            from app.models import utcnow
            from app.services.reviews import review_entries
            items = {str(c.id): {"score": 9, "comment": ""} for _, c in review_entries(s, r)}
            sa = SelfAssessment(review_id=rid, items=items, submitted_at=utcnow())
        s.add_all([r, sa])
        s.commit()
    try:
        j = client.get(f"/reviews/{rid}/johari", headers=manager).json()
        assert [q["key"] for q in j["quadrants"]] == ["arena", "blind", "facade", "unknown"]
        assert sum(len(q["items"]) for q in j["quadrants"]) >= 5
        piotr = _login(client, "piotr.nowak@demo.gov.pl")
        assert client.get(f"/reviews/{rid}/johari", headers=piotr).status_code == 403
    finally:
        with Session(engine) as s:
            r = s.get(Review, rid)
            r.status = old
            s.add(r)
            if created:
                s.delete(s.exec(select(SelfAssessment).where(SelfAssessment.review_id == rid)).one())
            s.commit()


def test_ipr_actions_follow_70_20_10_and_smart_check(client, manager):
    team = {e["full_name"]: e for e in client.get("/employees", headers=manager).json()}
    rid = team["Piotr Nowak"]["current_review"]["id"]
    review = client.get(f"/reviews/{rid}", headers=manager).json()
    crits = [{"criterion_id": c["criterion_id"], "score": 3 if i == 0 else 7, "justification": "Konkretne sytuacje."}
             for i, c in enumerate(review["criteria"])]
    assert client.patch(f"/reviews/{rid}", headers=manager, json={"criteria": crits}).status_code == 200
    ipr = client.post(f"/reviews/{rid}/ipr/generate", headers=manager).json()
    assert ipr["goals"]
    for g in ipr["goals"]:  # tryb bez modelu: działania w podziale praca / ludzie / szkolenie
        assert g["actions"].startswith("Praca:") and "Ludzie:" in g["actions"] and "Szkolenie:" in g["actions"]
    goals = [{"goal": "Poprawa komunikacji", "actions": "", "success_measure": "", "deadline": None, "criterion_id": None},
             {**{k: ipr["goals"][0][k] for k in ("goal", "actions", "success_measure", "deadline")},
              "criterion_id": ipr["goals"][0]["criterion_id"]}]
    r = client.post(f"/ipr/{ipr['id']}/ai/smart-check", headers=manager, json={"goals": goals})
    assert r.status_code == 200, r.text
    vague, good = r.json()["goals"]
    assert not vague["specific"] and not vague["measurable"] and not vague["time_bound"] and len(vague["issues"]) == 5
    assert vague["improved_measure"]
    assert good["relevant"] and good["time_bound"] and good["achievable"]
