"""Generowanie arkusza oceny okresowej (A/B/C) do pliku PDF - po stronie serwera.

Wzory arkuszy: załączniki nr 2-4 do rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r.
w sprawie warunków i sposobu przeprowadzania ocen okresowych (Dz. U. poz. 470).

Źródłem danych jest serializowana ocena (`services.reviews.serialize_review`), dzięki czemu PDF
i widok w aplikacji korzystają z tych samych pól i tych samych reguł ukrywania ocen
(np. pracownik przed zapoznaniem nie widzi ocen cząstkowych przełożonego).

Polskie znaki wymagają czcionki TrueType (DejaVu) - standardowe czcionki PDF nie mają Latin-2.
"""

from __future__ import annotations

import io
import os
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.scoring import SCALE

ANNEX = {"A": "2", "B": "3", "C": "4"}

# Przedziały średniej arytmetycznej i ogólne poziomy spełnienia kryteriów (§ 11 ust. 1 pkt 2).
LEVEL_RANGES = [
    ("od 1 punktu do 2 punktów", SCALE[1]),
    ("powyżej 2 punktów do 4 punktów", SCALE[3]),
    ("powyżej 4 punktów do 6 punktów", SCALE[5]),
    ("powyżej 6 punktów do 8 punktów", SCALE[7]),
    ("powyżej 8 punktów do 9 punktów", SCALE[9]),
]

SIGNATURE = {"system": "<potwierdzono w systemie>", "elektroniczny": "/podpis elektroniczny/", "wydruk": ""}

# Czcionka z polskimi znakami. DejaVu jest w obrazie backendu (fonts-dejavu-core);
# ścieżki alternatywne dla środowisk lokalnych.
_FONT_FILES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
_fonts_ready = False


def _ensure_fonts() -> None:
    global FONT, FONT_BOLD, _fonts_ready
    if _fonts_ready:
        return
    for regular, bold in _FONT_FILES:
        if os.path.exists(regular):
            pdfmetrics.registerFont(TTFont("Arkusz", regular))
            FONT = "Arkusz"
            FONT_BOLD = "Arkusz"
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("Arkusz-Bold", bold))
                FONT_BOLD = "Arkusz-Bold"
            break
    _fonts_ready = True


def _esc(text: Any) -> str:
    s = "" if text is None else str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\n", "<br/>")


def _date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    except ValueError:
        return value


def _x(on: bool) -> str:
    return "X" if on else ""


def _num(value: float | None) -> str:
    return f"{value:.2f}".replace(".", ",") if value is not None else ""


class _Doc:
    """Style i drobne komponenty arkusza (żeby uniknąć powtarzania w każdej sekcji)."""

    def __init__(self) -> None:
        _ensure_fonts()
        base = ParagraphStyle("base", fontName=FONT, fontSize=9, leading=11, alignment=TA_JUSTIFY)
        self.body = base
        self.small = ParagraphStyle("small", parent=base, fontSize=7.5, leading=9, alignment=TA_LEFT)
        self.right = ParagraphStyle("right", parent=base, fontSize=8, leading=10, alignment=TA_RIGHT)
        self.title = ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=12, leading=15, alignment=TA_CENTER)
        self.h = ParagraphStyle("h", parent=base, fontName=FONT_BOLD, fontSize=10, leading=13, alignment=TA_LEFT,
                                spaceBefore=6, spaceAfter=2)
        self.cell = ParagraphStyle("cell", parent=base, fontSize=8, leading=10, alignment=TA_LEFT)
        self.cell_c = ParagraphStyle("cell_c", parent=self.cell, alignment=TA_CENTER)
        self.head = ParagraphStyle("head", parent=self.cell, fontName=FONT_BOLD, fontSize=7.5, leading=9)
        self.head_c = ParagraphStyle("head_c", parent=self.head, alignment=TA_CENTER)
        self.tiny = ParagraphStyle("tiny", parent=self.head, fontSize=6, leading=7, alignment=TA_CENTER)

    def p(self, text: Any, style: ParagraphStyle | None = None) -> Paragraph:
        return Paragraph(_esc(text), style or self.cell)

    def markup(self, text: Any, style: ParagraphStyle | None = None) -> Paragraph:
        """Jak `p`, ale treść jest już znacznikami (np. <b>, <br/>) - dane dynamiczne escape'owane osobno."""
        return Paragraph(str(text), style or self.cell)

    def box(self, text: Any, min_height: int | None = 60, raw: bool = False) -> Table:
        kwargs = {"rowHeights": [min_height]} if min_height else {}
        para = self.markup(text or " ") if raw else self.p(text or " ")
        t = Table([[para]], colWidths=[180 * mm], **kwargs)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 3)]))
        return t

    def grid(self, data: list[list[Any]], widths: list[float], spans: list[tuple] | None = None) -> Table:
        t = Table(data, colWidths=widths, repeatRows=1)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for cell in spans or []:
            style.append(("SPAN", cell[0], cell[1]))
        t.setStyle(TableStyle(style))
        return t

    def signature(self, place: str, when: str | None, label: str, *, name: str | None = None,
                  name_label: str = "imię i nazwisko lub pieczątka ocenianego", method: str = "system") -> Table:
        has_name = name is not None
        top = [
            self.p(place if when else "", self.cell),
            self.p(_date(when), self.cell_c),
        ]
        if has_name:
            top.append(self.p(name if when else "", self.cell))
        top.append(self.p(SIGNATURE.get(method, "") if when else "", self.cell_c))
        bottom = [self.p("miejscowość", self.tiny), self.p("data (dd.mm.rrrr)", self.tiny)]
        if has_name:
            bottom.append(self.p(name_label, self.tiny))
        bottom.append(self.p(label, self.tiny))
        n = len(top)
        t = Table([top, bottom], colWidths=[180 * mm / n] * n, rowHeights=[22, 12])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, 0), 0.5, colors.black),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
        return t


def render_review_pdf(data: dict[str, Any]) -> bytes:
    """Buduje arkusz oceny (części I-III + zawiadomienia o zmianie terminu) i zwraca bajty PDF."""
    d = _Doc()
    sheet = data.get("sheet_type", "C")
    emp_form = data.get("employee_form") or {}
    reviewer_form = data.get("reviewer_form") or {}
    office = data.get("office") or {}
    criteria = data.get("criteria") or []
    mandatory = [c for c in criteria if not c.get("is_additional")]
    additional = [c for c in criteria if c.get("is_additional")]
    summary = data.get("summary")
    civil = bool((data.get("employee") or {}).get("is_civil_servant"))

    story: list[Any] = []

    # ------------------------------------------------------------------ nagłówek
    story.append(d.markup(f"Załącznik nr {ANNEX.get(sheet, '4')}<br/>WZÓR", d.right))
    story.append(Spacer(1, 4 * mm))
    story.append(d.p(f"ARKUSZ {sheet}", d.title))
    story.append(d.p("OCENA OKRESOWA", d.title))
    story.append(d.p("URZĘDNIKA SŁUŻBY CYWILNEJ LUB PRACOWNIKA SŁUŻBY CYWILNEJ", d.title))
    if (data.get("attempt") or 1) > 1:
        story.append(Spacer(1, 1 * mm))
        story.append(d.p("(ocena sporządzona po raz drugi w wyniku uwzględnienia sprzeciwu)", d.cell_c))
    story.append(Spacer(1, 4 * mm))

    # ------------------------------------------------------------------ CZĘŚĆ I
    story.append(d.p("CZĘŚĆ I", d.h))
    rows: list[list[Any]] = [[d.p("NAZWA URZĘDU", d.head), d.p(office.get("name", ""))]]
    spans: list[tuple] = []
    for title, person in (("DANE OCENIANEGO", emp_form), ("DANE OCENIAJĄCEGO", reviewer_form)):
        spans.append(((0, len(rows)), (1, len(rows))))
        rows += _people_rows(d, title, person, sheet)
    story.append(d.grid(rows, [60 * mm, 120 * mm], spans=spans))
    story.append(Spacer(1, 3 * mm))

    crit_rows: list[list[Any]] = [
        [d.p("KRYTERIA OCENY I TERMIN SPORZĄDZENIA OCENY", d.head_c), ""],
        [d.p("Kryteria obowiązkowe", d.head), d.p("Kryteria dodatkowe wybrane przez oceniającego (nie więcej niż 3)", d.head)],
    ]
    for i in range(max(len(mandatory), 3)):
        extra = additional[i]["name"] if i < len(additional) else (("brak" if not additional else "") if i == 0 else "")
        crit_rows.append([d.p(mandatory[i]["name"] if i < len(mandatory) else ""), d.p(extra)])
    crit_rows.append([d.p("Termin sporządzenia oceny", d.head),
                      d.p(f"{_date((data.get('deadlines') or {}).get('due_date'))} (dd.mm.rrrr)")])
    story.append(d.grid(crit_rows, [90 * mm, 90 * mm], spans=[((0, 0), (1, 0))]))
    story.append(Spacer(1, 2 * mm))
    story.append(d.markup(
        "Potwierdzamy:<br/>"
        "• przeprowadzenie rozmowy, o której mowa w § 5 ust. 1 rozporządzenia Prezesa Rady Ministrów z dnia "
        "4 kwietnia 2016 r. w sprawie warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej "
        "i pracowników służby cywilnej (Dz. U. poz. 470), i omówienie w trakcie tej rozmowy wszystkich wymaganych "
        "zagadnień,<br/>"
        "• zapoznanie ocenianego z kryteriami oceny oraz terminem sporządzenia oceny.", d.small))
    story.append(Spacer(1, 2 * mm))
    story.append(d.signature(data.get("criteria_reviewer_place", ""), data.get("criteria_reviewer_confirmed_at"),
                             "podpis oceniającego", method=data.get("signature_method", "system")))
    story.append(Spacer(1, 2 * mm))
    story.append(d.signature(data.get("criteria_employee_place", ""), data.get("criteria_employee_confirmed_at"),
                             "podpis ocenianego", method=data.get("signature_method", "system")))

    # ------------------------------------------------------------------ CZĘŚĆ II
    story.append(PageBreak())
    story.append(d.p("CZĘŚĆ II", d.h))
    story.append(d.grid(
        [
            [d.p("DATA PRZEPROWADZENIA ROZMOWY OCENIAJĄCEJ", d.head),
             d.p(f"{_date(data.get('conversation_date'))} (dd.mm.rrrr)".strip())],
            [d.p("OKRES, W KTÓRYM OCENIANY PODLEGAŁ OCENIE", d.head),
             d.p(f"OD: {_date(data.get('period_start'))}   DO: {_date(data.get('period_end'))}")],
        ],
        [90 * mm, 90 * mm]))
    story.append(Spacer(1, 3 * mm))

    story.append(_criteria_matrix(d, mandatory, additional))
    story.append(Spacer(1, 2 * mm))
    story.append(d.markup(f"Średnia arytmetyczna z ocen cząstkowych przyznanych za poszczególne kryteria oceny: "
                          f"<b>{_num((summary or {}).get('average'))}</b>"))
    story.append(Spacer(1, 3 * mm))

    story.append(d.p("PRZYZNANIE OCENY", d.h))
    story.append(d.p("Należy wstawić znak „X” w odpowiednie pole", d.small))
    level_rows = [[d.p("", d.head_c),
                   d.p("Liczba punktów stanowiąca średnią arytmetyczną ze wszystkich ocen cząstkowych", d.head),
                   d.p("Ogólny poziom spełnienia kryteriów oceny", d.head)]]
    for rng, level in LEVEL_RANGES:
        level_rows.append([d.p(_x(bool(summary and summary.get("complete") and summary.get("level") == level)), d.cell_c),
                           d.p(rng), d.p(level)])
    story.append(d.grid(level_rows, [10 * mm, 85 * mm, 85 * mm]))
    story.append(Spacer(1, 3 * mm))

    story.append(d.grid(
        [
            [d.p("OCENA OKRESOWA W SŁUŻBIE CYWILNEJ", d.head_c), "", "", ""],
            [d.p("POZYTYWNA", d.head), d.p(_x(bool(summary and summary.get("result") == "pozytywna")), d.cell_c),
             d.p("NEGATYWNA", d.head), d.p(_x(bool(summary and summary.get("result") == "negatywna")), d.cell_c)],
        ],
        [45 * mm] * 4, spans=[((0, 0), (3, 0))]))
    story.append(Spacer(1, 3 * mm))

    story.append(d.p("UZASADNIENIE PRZYZNANEJ OCENY OKRESOWEJ", d.h))
    just = _esc(data.get("justification") or "")
    per_crit = [c for c in criteria if c.get("justification")]
    if per_crit:
        just += "".join(f"<br/><i>{_esc(c['name'])}</i> – {_esc(c['justification'])}" for c in per_crit)
    story.append(d.box(just, raw=True))
    story.append(Spacer(1, 3 * mm))

    story.append(d.p("WNIOSKI DOTYCZĄCE INDYWIDUALNEGO PROGRAMU ROZWOJU ZAWODOWEGO", d.h))
    story.append(d.box(data.get("ipr_conclusions") or "", min_height=55))

    if civil:
        story.append(Spacer(1, 3 * mm))
        story.append(d.grid(
            [
                [d.p("DANE DOTYCZĄCE POPRZEDNIEJ OCENY OKRESOWEJ URZĘDNIKA SŁUŻBY CYWILNEJ", d.head), "", ""],
                [d.p(f"Ocena: {data.get('prev_result') or ''}"),
                 d.p(f"Poziom: {'' if data.get('prev_result') == 'brak' else data.get('prev_level') or ''}"),
                 d.p(f"Data sporządzenia: {'' if data.get('prev_result') == 'brak' else _date(data.get('prev_date'))}")],
            ],
            [60 * mm] * 3, spans=[((0, 0), (2, 0))]))

    story.append(Spacer(1, 3 * mm))
    story.append(d.grid(
        [
            [d.p("CZY DO OCENY OKRESOWEJ DOŁĄCZONO WNIOSEK O PRZYZNANIE KOLEJNEGO STOPNIA SŁUŻBOWEGO?", d.head),
             "", "", "", "", ""],
            [d.p("TAK", d.head), d.p(_x(data.get("promotion_request") == "tak"), d.cell_c),
             d.p("NIE", d.head), d.p(_x(data.get("promotion_request") == "nie"), d.cell_c),
             d.p("NIE DOTYCZY (oceniany jest pracownikiem służby cywilnej)", d.head),
             d.p(_x(data.get("promotion_request") == "nie_dotyczy"), d.cell_c)],
        ],
        [14 * mm, 10 * mm, 14 * mm, 10 * mm, 100 * mm, 32 * mm], spans=[((0, 0), (5, 0))]))

    story.append(Spacer(1, 4 * mm))
    rows2: list[list[Any]] = _people_rows(d, "DANE OCENIAJĄCEGO", reviewer_form, sheet)
    story.append(d.grid(rows2, [60 * mm, 120 * mm], spans=[((0, 0), (1, 0))]))
    story.append(Spacer(1, 2 * mm))
    story.append(d.signature(data.get("reviewer_place", ""), data.get("reviewer_signed_at"), "podpis oceniającego",
                             method=data.get("signature_method", "system")))

    story.append(Spacer(1, 4 * mm))
    story.append(d.p("Przeprowadzono ze mną rozmowę oceniającą oraz zapoznałem(-łam) się z oceną okresową i wnioskami "
                     "dotyczącymi indywidualnego programu rozwoju zawodowego."))
    ack_date = None if data.get("ack_fiction") else data.get("acknowledged_at")
    story.append(d.signature(data.get("employee_place", ""), ack_date, "podpis ocenianego",
                             name=(data.get("employee") or {}).get("full_name", ""),
                             method=data.get("signature_method", "system")))
    if data.get("ack_fiction"):
        story.append(Spacer(1, 1 * mm))
        story.append(d.p(f"Adnotacja: stwierdzono doręczenie informacji o ocenie ({_date(data.get('acknowledged_at'))}) "
                         f"bez potwierdzenia zapoznania przez ocenianego. {data.get('ack_fiction_note') or ''}",
                         d.small))

    story.append(Spacer(1, 3 * mm))
    story.append(d.box(
        "POUCZENIE<br/>Na podstawie art. 83 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie cywilnej od oceny "
        f"okresowej służy, w terminie 7 dni od dnia zapoznania się z oceną, sprzeciw do "
        f"{_esc(data.get('objection_body') or office.get('objection_body') or 'dyrektora generalnego urzędu')}.",
        min_height=None, raw=True))

    # ------------------------------------------------------------------ CZĘŚĆ III
    if civil and data.get("promotion_request") == "tak":
        story.append(PageBreak())
        story.append(d.p("CZĘŚĆ III", d.h))
        story.append(d.p("Wniosek jest wypełniany i dołączany do arkusza oceny okresowej ocenianego tylko w sytuacji "
                         "skorzystania przez oceniającego z możliwości przewidzianej w art. 89 ust. 1 ustawy z dnia "
                         "21 listopada 2008 r. o służbie cywilnej.", d.small))
        story.append(Spacer(1, 2 * mm))
        story.append(d.grid(
            [
                [d.p("DANE URZĘDNIKA SŁUŻBY CYWILNEJ", d.head), ""],
                [d.p("Imię", d.cell), d.p(emp_form.get("first_name", ""))],
                [d.p("Nazwisko", d.cell), d.p(emp_form.get("last_name", ""))],
                [d.p("Rok mianowania", d.cell), d.p(data.get("appointment_year") or "")],
                [d.p("Posiadany stopień służbowy", d.cell),
                 d.p(data.get("civil_grade_label") or data.get("civil_grade") or "")],
                [d.p("Data przyznania stopnia służbowego", d.cell), d.p(_date(data.get("civil_grade_date")))],
            ],
            [60 * mm, 120 * mm], spans=[((0, 0), (1, 0))]))
        story.append(Spacer(1, 3 * mm))
        story.append(d.p("WNIOSEK O PRZYZNANIE URZĘDNIKOWI SŁUŻBY CYWILNEJ KOLEJNEGO STOPNIA SŁUŻBOWEGO", d.h))
        full_name = (data.get("employee") or {}).get("full_name", "")
        story.append(d.markup(f"W związku z uzyskaniem przez Panią/Pana <b>{_esc(full_name)}</b> pozytywnej oceny "
                              f"okresowej, na podstawie art. 89 ust. 1 ustawy z dnia 21 listopada 2008 r. o służbie "
                              f"cywilnej wnioskuję o przyznanie "
                              f"<b>{_esc(data.get('promotion_target') or '……')}</b> stopnia służbowego."))
        story.append(Spacer(1, 3 * mm))
        story.append(d.p("UMOTYWOWANIE WNIOSKU", d.h))
        story.append(d.box(data.get("promotion_justification") or "", min_height=90))
        story.append(Spacer(1, 2 * mm))
        story.append(d.signature(data.get("reviewer_place", ""), data.get("reviewer_signed_at"), "podpis oceniającego",
                                 name=reviewer_form.get("full_name", ""),
                                 name_label="imię i nazwisko lub pieczątka oceniającego",
                                 method=data.get("signature_method", "system")))

    # ------------------------------------ § 8: zawiadomienia o zmianie terminu (kopie do arkusza)
    for entry in data.get("due_date_history") or []:
        reason = entry.get("reason") or ""
        if "art. 81 ust. 8" not in reason or "zmiana oceniającego na:" in reason:
            continue
        story.append(PageBreak())
        story += _notice(d, data, office, emp_form, reviewer_form, entry)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Arkusz oceny {sheet}", author=office.get("name", ""),
    )
    doc.build(story)
    return buf.getvalue()


def _people_rows(d: _Doc, title: str, person: dict[str, Any], sheet: str) -> list[list[Any]]:
    fields = [("Imię", person.get("first_name", "")), ("Nazwisko", person.get("last_name", "")),
              ("Komórka organizacyjna", person.get("department", "")), ("Stanowisko pracy", person.get("position", ""))]
    if sheet == "A":
        fields = [f for f in fields if f[0] != "Komórka organizacyjna"]
    rows: list[list[Any]] = [[d.p(title, d.head_c), ""]]
    rows += [[d.p(k, d.cell), d.p(v)] for k, v in fields]
    return rows


def _criteria_matrix(d: _Doc, mandatory: list[dict], additional: list[dict]) -> Table:
    head = [d.p("KRYTERIA OBOWIĄZKOWE", d.head)]
    for value, label in SCALE.items():
        head.append(d.markup(f"{_esc(label)}<br/>{value} "
                             + ("punkt" if value == 1 else "punkty" if value < 5 else "punktów"), d.tiny))
    rows = [head]
    for c in mandatory:
        rows.append([d.p(c["name"])] + [d.p(_x(c.get("score") == v), d.cell_c) for v in SCALE])
    rows.append([d.p("KRYTERIA DODATKOWE WYBRANE PRZEZ OCENIAJĄCEGO", d.head), d.p("OCENA CZĄSTKOWA", d.head_c), "", "", "", ""])
    spans = [((1, len(rows) - 1), (5, len(rows) - 1))]
    for i in range(3):
        c = additional[i] if i < len(additional) else None
        name = c["name"] if c else ("brak" if not additional else "" if i > 0 else "")
        rows.append([d.p(name)] + [d.p(_x(bool(c and c.get("score") == v)), d.cell_c) for v in SCALE])
    return d.grid(rows, [60 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm], spans=spans)


def _notice(d: _Doc, data: dict, office: dict, emp_form: dict, reviewer_form: dict, entry: dict) -> list[Any]:
    story: list[Any] = []
    story.append(d.grid([[d.p(office.get("name", "")), d.p(f"{office.get('city', '')}, {_date(entry.get('at'))}", d.right)]],
                        [90 * mm, 90 * mm]))
    story.append(Spacer(1, 12 * mm))
    story.append(Table([[d.p(""), d.markup(f"Pani/Pan<br/><b>{_esc((data.get('employee') or {}).get('full_name', ''))}"
                                         f"</b><br/>{_esc(emp_form.get('position', ''))}")]],
                       colWidths=[90 * mm, 90 * mm]))
    story.append(Spacer(1, 10 * mm))
    story.append(d.p("ZAWIADOMIENIE O ZMIANIE TERMINU SPORZĄDZENIA OCENY OKRESOWEJ", d.title))
    story.append(Spacer(1, 6 * mm))
    from_part = f" ustalony na dzień {_date(entry.get('from'))}" if entry.get("from") else ""
    story.append(d.markup("Na podstawie § 8 rozporządzenia Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. w sprawie "
                          "warunków i sposobu przeprowadzania ocen okresowych urzędników służby cywilnej i pracowników "
                          "służby cywilnej (Dz. U. poz. 470) zawiadamiam, że termin sporządzenia Pani/Pana oceny okresowej "
                          f"na piśmie{from_part} został zmieniony na dzień <b>{_date(entry.get('date'))}</b>."))
    story.append(Spacer(1, 2 * mm))
    story.append(d.p(f"Podstawa zmiany: {entry.get('reason')}."))
    if entry.get("note"):
        story.append(Spacer(1, 2 * mm))
        story.append(d.p(f"Uzasadnienie: {entry.get('note')}"))
    story.append(Spacer(1, 6 * mm))
    story.append(d.signature(office.get("city", ""), entry.get("at"), "podpis oceniającego",
                             name=reviewer_form.get("full_name", ""),
                             name_label="imię i nazwisko lub pieczątka oceniającego",
                             method=data.get("signature_method", "system")))
    story.append(Spacer(1, 8 * mm))
    story.append(d.p("Kopię pisma dołącza się do arkusza oceny okresowej (§ 8 rozporządzenia).", d.tiny))
    return story
