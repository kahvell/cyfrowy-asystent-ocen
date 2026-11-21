"""Tabele bazy danych (SQLModel). Opis modelu: ARCHITECTURE.md, sekcja 5."""

from datetime import UTC, date, datetime
from typing import Any

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- Struktura organizacyjna ---------------------------------------------------------


class Office(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    city: str = ""  # domyślna miejscowość w arkuszu
    objection_body: str = "dyrektora generalnego urzędu"  # pouczenie (art. 83 ust. 1); w arkuszu A - inny organ


class Department(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    office_id: int = Field(foreign_key="office.id")
    name: str


class Employee(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    full_name: str
    gender: str | None = None  # "K" / "M" - tylko do zagregowanej analizy stronniczości (k-anonimowość)
    position: str
    department_id: int = Field(foreign_key="department.id")
    manager_id: int | None = Field(default=None, foreign_key="employee.id")
    position_description: str = Field(default="", sa_type=Text)
    # arkusz wg rozporządzenia: A - kierownik urzędu, B - bezpośrednie kierowanie, C - pozostali
    sheet_type: str = "C"
    is_civil_servant: bool = False  # urzędnik (mianowany) vs pracownik służby cywilnej
    # nawiązanie stosunku pracy na czas nieokreślony / mianowanie - początek pierwszego okresu oceny
    employment_start: date | None = None
    appointment_year: int | None = None  # rok mianowania (urzędnik)
    civil_grade: int | None = None       # posiadany stopień służbowy 1-9 (art. 89)
    civil_grade_date: date | None = None
    active: bool = True                   # False po ustaniu stosunku pracy (dane w archiwum akt)
    # wyższe stanowisko w służbie cywilnej (art. 52 ustawy) - bez IPR (art. 108 ust. 1)
    senior_position: bool = False
    employment_end: date | None = None


class Absence(SQLModel, table=True):
    """Nieobecności usprawiedliwione - przedłużają termin oceny (art. 81 ust. 7)."""
    id: int | None = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    start: date
    end: date
    kind: str = "zwolnienie lekarskie"  # zwolnienie lekarskie | urlop wypoczynkowy | urlop rodzicielski | inne


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str
    password_hash: str
    role: str  # employee | manager | hr | admin
    employee_id: int | None = Field(default=None, foreign_key="employee.id")


# --- Kryteria i cykle -----------------------------------------------------------------


class Criterion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    name: str
    description: str = Field(default="", sa_type=Text)
    behavioral_indicators: list[str] = Field(default_factory=list, sa_type=JSON)
    mandatory_for: list[str] = Field(default_factory=list, sa_type=JSON)  # np. ["B", "C"]
    keywords: list[str] = Field(default_factory=list, sa_type=JSON)
    order: int = 0


class ReviewCycle(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    period_start: date
    period_end: date
    status: str = "open"  # open | closed


# --- Dziennik obserwacji --------------------------------------------------------------


class Note(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    author_id: int = Field(foreign_key="user.id")
    date: date
    text: str = Field(sa_type=Text)
    sentiment: str | None = None  # positive | neutral | negative
    source: str = "manager"  # manager | self
    classified: bool = False
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class NoteCriterion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("note_id", "criterion_id"),)
    id: int | None = Field(default=None, primary_key=True)
    note_id: int = Field(foreign_key="note.id", index=True)
    criterion_id: int = Field(foreign_key="criterion.id")
    confidence: float = 1.0
    assigned_by: str = "ai"  # ai | human


# --- Ocena ----------------------------------------------------------------------------


class Review(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("employee_id", "cycle_id"),)
    id: int | None = Field(default=None, primary_key=True)
    employee_id: int = Field(foreign_key="employee.id", index=True)
    reviewer_id: int = Field(foreign_key="user.id")
    cycle_id: int = Field(foreign_key="reviewcycle.id")
    # Etap I:  criteria (wyznaczenie kryteriów i rozmowa rozpoczynająca, potwierdzenia obu stron)
    #          -> observation (okres oceny, dziennik obserwacji)
    # Etap II: draft -> submitted (gotowa do rozmowy) -> discussed (po rozmowie oceniającej)
    #          -> final (sporządzona i przekazana do zapoznania) -> acknowledged (zapoznanie / fikcja zapoznania)
    #          -> objection (sprzeciw, art. 83) -> acknowledged | discussed (zmiana) | draft (ponowne sporządzenie)
    status: str = "draft"
    sheet_type: str = "C"
    period_start: date
    period_end: date
    conversation_date: date | None = None
    # --- Część I arkusza: kryteria, termin, rozmowa rozpoczynająca (§ 5) ---
    criteria_deadline: date | None = None
    due_date: date | None = None              # termin sporządzenia oceny
    due_date_history: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
    opening_conversation_date: date | None = None
    opening_notes: str = Field(default="", sa_type=Text)  # oczekiwania, cele, ustalenia z rozmowy
    criteria_reviewer_confirmed_at: date | None = None
    criteria_reviewer_place: str = ""
    criteria_employee_confirmed_at: date | None = None
    criteria_employee_place: str = ""
    # --- Część II: poprzednia ocena urzędnika, podpisy, zapoznanie ---
    prev_result: str | None = None   # pozytywna | negatywna | brak
    prev_level: str | None = None
    prev_date: date | None = None
    reviewer_place: str = ""
    reviewer_signed_at: date | None = None
    employee_place: str = ""
    acknowledged_at: date | None = None
    ack_fiction: bool = False         # „fikcja zapoznania” - informacja doręczona, brak potwierdzenia
    ack_fiction_note: str = ""
    # --- Część III: wniosek o kolejny stopień służbowy (art. 89 ust. 1) ---
    promotion_request: str = "nie_dotyczy"  # tak | nie | nie_dotyczy
    appointment_year: int | None = None
    civil_grade: int | None = None
    civil_grade_date: date | None = None
    promotion_justification: str = Field(default="", sa_type=Text)
    # --- Sprzeciw (art. 83) ---
    objection_at: date | None = None
    objection_text: str = Field(default="", sa_type=Text)
    objection_decision: str | None = None  # odrzucony | zmiana | ponowne_sporzadzenie
    objection_decided_at: date | None = None
    attempt: int = 1  # 2 = ocena sporządzana po raz drugi po uwzględnieniu sprzeciwu
    overall_score: float | None = None
    overall_level: str | None = None
    result: str | None = None  # pozytywna | negatywna
    justification: str = Field(default="", sa_type=Text)
    ipr_conclusions: str = Field(default="", sa_type=Text)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)
    submitted_at: NaiveDatetime | None = None
    finalized_at: NaiveDatetime | None = None


class ReviewCriterion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("review_id", "criterion_id"),)
    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id", index=True)
    criterion_id: int = Field(foreign_key="criterion.id")
    is_additional: bool = False
    score: int | None = None
    justification: str = Field(default="", sa_type=Text)
    source_note_ids: list[int] = Field(default_factory=list, sa_type=JSON)


class SelfAssessment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id", unique=True)
    # {"<criterion_id>": {"score": 7, "comment": "..."}}
    items: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    summary: str = Field(default="", sa_type=Text)
    submitted_at: NaiveDatetime | None = None
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


# --- AI (human-in-the-loop) -----------------------------------------------------------


class AISuggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    review_id: int | None = Field(default=None, foreign_key="review.id", index=True)
    criterion_id: int | None = Field(default=None, foreign_key="criterion.id")
    kind: str  # draft_justification | quality_check | compare_self | ipr | classify_note
    payload: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    model: str
    prompt_version: str
    status: str = "pending"  # pending | accepted | edited | rejected | info
    final_payload: dict[str, Any] | None = Field(default=None, sa_type=JSON)
    created_by: int | None = Field(default=None, foreign_key="user.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    decided_by: int | None = Field(default=None, foreign_key="user.id")
    decided_at: NaiveDatetime | None = None


# --- IPR ------------------------------------------------------------------------------


class Training(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    title: str
    description: str = Field(default="", sa_type=Text)
    criterion_codes: list[str] = Field(default_factory=list, sa_type=JSON)
    format: str = "stacjonarne"
    hours: int = 8


class IPR(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id", unique=True)
    employee_id: int = Field(foreign_key="employee.id")
    # art. 108 ustawy: ustala bezpośredni przełożony -> akceptuje kierujący komórką -> zatwierdza dyrektor generalny
    status: str = "draft"  # draft | established | accepted | approved
    summary: str = Field(default="", sa_type=Text)
    ai_suggestion_id: int | None = Field(default=None, foreign_key="aisuggestion.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)
    established_at: NaiveDatetime | None = None
    accepted_at: NaiveDatetime | None = None
    accepted_by: int | None = Field(default=None, foreign_key="user.id")
    approved_at: NaiveDatetime | None = None
    approved_by: int | None = Field(default=None, foreign_key="user.id")


class IPRGoal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    ipr_id: int = Field(foreign_key="ipr.id", index=True)
    criterion_id: int | None = Field(default=None, foreign_key="criterion.id")
    goal: str = Field(sa_type=Text)
    actions: str = Field(default="", sa_type=Text)
    success_measure: str = Field(default="", sa_type=Text)
    deadline: date | None = None
    training_id: int | None = Field(default=None, foreign_key="training.id")


# --- RAG ------------------------------------------------------------------------------


class LegalDoc(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    source: str
    file_name: str | None = None     # plik w seed/legal - aktualizacja przepisu = podmiana pliku
    content_hash: str | None = None  # zmiana treści -> automatyczne ponowne zaindeksowanie


class DocChunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    doc_id: int = Field(foreign_key="legaldoc.id", index=True)
    ref: str
    text: str = Field(sa_type=Text)
    embedding: list[float] | None = Field(default=None, sa_type=JSON)


# --- Audyt ----------------------------------------------------------------------------


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int | None = Field(default=None, foreign_key="user.id")
    action: str
    entity: str
    entity_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict, sa_type=JSON)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


# --- Wnioski i powiadomienia ------------------------------------------------------------


class DueDateRequest(SQLModel, table=True):
    """Wniosek ocenianego o zmianę terminu oceny (art. 81 ust. 8 pkt 4) - rozpatruje oceniający."""
    id: int | None = Field(default=None, primary_key=True)
    review_id: int = Field(foreign_key="review.id", index=True)
    requested_by: int = Field(foreign_key="user.id")
    proposed_date: date
    reason: str = Field(sa_type=Text)
    status: str = "pending"  # pending | accepted | rejected
    decision_note: str = ""
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    decided_at: NaiveDatetime | None = None


class Notification(SQLModel, table=True):
    """Powiadomienia w systemie; przy skonfigurowanym SMTP wysyłane też e-mailem."""
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    subject: str
    body: str = Field(default="", sa_type=Text)
    link: str = ""
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    read_at: NaiveDatetime | None = None
    emailed_at: NaiveDatetime | None = None
