"""Fikcyjny urząd do demo. Wszystkie osoby i zdarzenia są zmyślone."""

import unicodedata
from datetime import date

DEMO_PASSWORD = "demo123"
DEMO_EMAIL_DOMAIN = "demo.gov.pl"

# „ł/Ł” nie mają rozkładu NFKD (w odróżnieniu od ą, ć, ę, ń, ó, ś, ź, ż) - transliterujemy je ręcznie
_PL_DIACRITICS = str.maketrans({"ł": "l", "Ł": "L"})


def email_for(full_name: str) -> str:
    """Służbowy adres demo w formacie imie.nazwisko@demo.gov.pl (polskie znaki transliterowane).

    Przykłady: „Tomasz Wójcik” -> tomasz.wojcik@demo.gov.pl, „Łukasz Michalski” -> lukasz.michalski@demo.gov.pl.
    W urzędzie format adresu bywa inny - dlatego w zakładce Kadry e-mail można edytować ręcznie.
    """
    ascii_name = unicodedata.normalize("NFKD", full_name.translate(_PL_DIACRITICS)).encode("ascii", "ignore").decode()
    local = ".".join(part for part in ascii_name.lower().split() if part)
    return f"{local}@{DEMO_EMAIL_DOMAIN}"


OFFICE = "Urząd Wojewódzki w Przykładowie (dane fikcyjne)"

PREV_CYCLE = ("Ocena 2022–2024", date(2022, 12, 1), date(2024, 11, 30))
CUR_CYCLE = ("Ocena 2024–2026", date(2024, 12, 1), date(2026, 11, 30))

# dział: (kierownik, e-mail kierownika, średnia ocen w poprzednim cyklu - do kalibracji, pracownicy)
# pracownik: (imię i nazwisko, płeć, stanowisko, urzędnik?)
DEPARTMENTS = [
    {
        "name": "Wydział Cyfryzacji",
        "head": ("Marek Zieliński", "M", "Naczelnik Wydziału Cyfryzacji"),
        "email": email_for("Marek Zieliński"),
        "bias": 0.0,
        "staff": [
            ("Anna Kowalska", "K", "Starszy specjalista ds. systemów informatycznych", True,
             "Administrowanie systemami dziedzinowymi urzędu, przygotowywanie dokumentacji zamówień IT, "
             "wsparcie wdrożeń e-usług, koordynacja współpracy z dostawcami."),
            ("Piotr Nowak", "M", "Specjalista ds. bezpieczeństwa teleinformatycznego", False,
             "Monitorowanie bezpieczeństwa sieci, obsługa incydentów, zarządzanie certyfikatami i kopiami zapasowymi."),
            ("Katarzyna Wiśniewska", "K", "Inspektor ds. e-usług", False,
             "Utrzymanie formularzy elektronicznych, kontakt z użytkownikami e-usług, raportowanie."),
            ("Tomasz Wójcik", "M", "Starszy inspektor ds. infrastruktury", False,
             "Utrzymanie infrastruktury serwerowej i sieciowej urzędu."),
            ("Magdalena Kamińska", "K", "Specjalista ds. analizy danych", True,
             "Przygotowywanie analiz i raportów zarządczych, utrzymanie hurtowni danych."),
            ("Jakub Lewandowski", "M", "Referent ds. wsparcia użytkowników", False,
             "Obsługa zgłoszeń helpdesk, konfiguracja stanowisk pracy."),
        ],
    },
    {
        "name": "Wydział Obsługi Klienta",
        "head": ("Ewa Dąbrowska", "K", "Naczelnik Wydziału Obsługi Klienta"),
        "email": email_for("Ewa Dąbrowska"),
        "bias": 2.2,  # oceniający „łagodny” - prawie wszyscy dostają 9
        "staff": [
            ("Joanna Szymańska", "K", "Inspektor ds. obsługi klienta", False, "Obsługa interesantów w punkcie kancelaryjnym."),
            ("Michał Woźniak", "M", "Inspektor ds. obsługi klienta", False, "Obsługa infolinii urzędu."),
            ("Agnieszka Kozłowska", "K", "Starszy inspektor ds. skarg i wniosków", True, "Rozpatrywanie skarg i wniosków."),
            ("Paweł Jankowski", "M", "Referent ds. obsługi klienta", False, "Obsługa kolejki i informacji ogólnej."),
            ("Monika Mazur", "K", "Inspektor ds. legalizacji dokumentów", False, "Legalizacja dokumentów."),
            ("Krzysztof Kwiatkowski", "M", "Specjalista ds. dostępności", False, "Koordynacja dostępności urzędu."),
        ],
    },
    {
        "name": "Wydział Finansów i Budżetu",
        "head": ("Andrzej Krawczyk", "M", "Naczelnik Wydziału Finansów i Budżetu"),
        "email": email_for("Andrzej Krawczyk"),
        "bias": -1.4,  # oceniający „surowy”
        "staff": [
            ("Barbara Piotrowska", "K", "Główny księgowy - specjalista", True, "Prowadzenie ksiąg rachunkowych."),
            ("Grzegorz Grabowski", "M", "Starszy specjalista ds. budżetu", True, "Planowanie i monitorowanie budżetu."),
            ("Aleksandra Pawłowska", "K", "Inspektor ds. płac", False, "Naliczanie wynagrodzeń."),
            ("Łukasz Michalski", "M", "Inspektor ds. rozliczeń", False, "Rozliczenia z kontrahentami."),
            ("Natalia Zając", "K", "Referent ds. księgowości", False, "Dekretacja dokumentów."),
            ("Rafał Król", "M", "Specjalista ds. kontroli finansowej", False, "Kontrola wydatków."),
        ],
    },
    {
        "name": "Wydział Kadr i Szkoleń",
        "head": ("Dorota Wieczorek", "K", "Naczelnik Wydziału Kadr i Szkoleń"),
        "email": email_for("Dorota Wieczorek"),
        "bias": 0.3,
        "staff": [
            ("Marta Jabłońska", "K", "Starszy specjalista ds. kadr", True, "Prowadzenie akt osobowych."),
            ("Adam Wróbel", "M", "Specjalista ds. szkoleń", False, "Planowanie szkoleń."),
            ("Karolina Majewska", "K", "Inspektor ds. naboru", False, "Prowadzenie naborów."),
            ("Marcin Olszewski", "M", "Inspektor ds. kadr", False, "Sprawy kadrowe."),
            ("Beata Stępień", "K", "Specjalista ds. wynagrodzeń i ZFŚS", False, "Obsługa ZFŚS."),
        ],
    },
]

EMPLOYEE_LOGIN = (email_for("Anna Kowalska"), "Anna Kowalska")
HR_USER = ("hr@demo.gov.pl", "Iwona Malinowska (HR)")
ADMIN_USER = ("admin@demo.gov.pl", "Administrator systemu")

# dyrektor generalny - bezpośredni przełożony naczelników wydziałów (art. 81 ust. 1 ustawy)
DIRECTOR_DEPT = "Dyrekcja"
DIRECTOR = ("Wacław Zawadzki", "M", "Dyrektor Generalny")
DIRECTOR_LOGIN = (email_for(DIRECTOR[0]), DIRECTOR[0])

# (data, tekst, kody kryteriów, sentyment, źródło)
NOTES: dict[str, list[tuple[date, str, list[str], str, str]]] = {
    "Anna Kowalska": [
        (date(2025, 1, 22), "Przeprowadziła dla zespołu szkolenie wewnętrzne z nowego systemu EZD; przygotowała instrukcję, z której korzysta cały wydział.", ["WSPOLPRACA", "WIEDZA"], "positive", "manager"),
        (date(2025, 3, 11), "Przygotowała specyfikację techniczną do zamówienia na serwery bezbłędnie i dwa dni przed terminem.", ["RZETELNOSC", "ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2025, 4, 29), "Odpowiedź na pismo z ministerstwa była nieczytelna dla adresata - zbyt techniczny język, trzeba było ją poprawić przed wysyłką.", ["KOMUNIKACJA"], "negative", "manager"),
        (date(2025, 6, 3), "Zaplanowała harmonogram migracji poczty dla 400 użytkowników i zrealizowała go zgodnie z planem, bez przestojów.", ["ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2025, 7, 15), "Zaproponowała automatyzację raportu miesięcznego (skrypt w Pythonie) - oszczędność ok. 6 godzin pracy miesięcznie.", ["KREATYWNOSC"], "positive", "manager"),
        (date(2025, 9, 2), "Przy awarii systemu kolejkowego w Wydziale Obsługi Klienta wspólnie z ich zespołem przywróciła działanie w 2 godziny.", ["WSPOLPRACA"], "positive", "manager"),
        (date(2025, 10, 20), "Na spotkaniu z dostawcą nie dała dojść do głosu przedstawicielowi finansów; ustalenia były niejasne i spotkanie trzeba było powtórzyć.", ["KOMUNIKACJA", "WSPOLPRACA"], "negative", "manager"),
        (date(2025, 11, 26), "Ukończyła kurs z cyberbezpieczeństwa i wdrożyła w wydziale zalecenia dotyczące haseł i kopii zapasowych.", ["WIEDZA"], "positive", "manager"),
        (date(2026, 1, 14), "Opóźniła o tydzień przekazanie dokumentacji powykonawczej i nie zgłosiła wcześniej problemu.", ["RZETELNOSC"], "negative", "manager"),
        (date(2026, 2, 24), "Po nagłym odejściu współpracownika samodzielnie ustaliła priorytety i utrzymała terminy projektu e-Doręczeń.", ["ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2026, 3, 10), "Zdobyłam certyfikat ITIL 4 Foundation (szkolenie dofinansowane przez urząd).", ["WIEDZA"], "positive", "self"),
        (date(2026, 4, 8), "Przygotowała jasną, dwustronicową notatkę dla dyrektora generalnego o ryzykach projektu - przyjętą bez poprawek.", ["KOMUNIKACJA"], "positive", "manager"),
        (date(2026, 5, 19), "Wdrażała nową osobę w zespole: przygotowała plan wdrożenia i co tydzień dzieliła się wiedzą.", ["WSPOLPRACA"], "positive", "manager"),
        (date(2026, 6, 30), "Audyt wewnętrzny nie wykazał żadnych błędów w prowadzonej przez nią ewidencji licencji.", ["RZETELNOSC"], "positive", "manager"),
        (date(2026, 8, 25), "Zaproponowała nowy sposób zgłaszania awarii przez formularz zamiast maili - czas obsługi zgłoszeń spadł o ok. 30%.", ["KREATYWNOSC", "ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2026, 9, 15), "Poprowadziłam prezentację o e-usługach na konferencji wojewódzkiej dla 120 osób.", ["KOMUNIKACJA"], "positive", "self"),
        (date(2026, 10, 7), "Przeanalizowała nowelizację przepisów o krajowym systemie cyberbezpieczeństwa i przygotowała zestawienie obowiązków dla wydziału.", ["WIEDZA"], "positive", "manager"),
        (date(2026, 11, 4), "Zrealizowała przed terminem wdrożenie nowej wersji systemu kadrowego.", ["ORGANIZACJA_PRACY", "RZETELNOSC"], "positive", "manager"),
    ],
    "Piotr Nowak": [
        (date(2025, 5, 12), "Zapomniał przedłużyć certyfikat SSL - strona urzędu była niedostępna przez 3 godziny.", ["RZETELNOSC"], "negative", "manager"),
        (date(2026, 9, 29), "Sprawnie obsłużył incydent phishingowy - zablokował konta i poinformował wszystkich pracowników.", ["RZETELNOSC", "KOMUNIKACJA"], "positive", "manager"),
        (date(2026, 10, 6), "Przygotował plan testów odtwarzania kopii zapasowych i zrealizował go zgodnie z harmonogramem.", ["ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2026, 10, 15), "Pomógł koledze z Wydziału Finansów w konfiguracji podpisu kwalifikowanego.", ["WSPOLPRACA"], "positive", "manager"),
        (date(2026, 10, 28), "Ukończył webinar o nowelizacji przepisów o cyberbezpieczeństwie.", ["WIEDZA"], "positive", "manager"),
        (date(2026, 11, 5), "Terminowo przygotował raport kwartalny o incydentach.", ["RZETELNOSC"], "positive", "manager"),
        (date(2026, 11, 13), "Dobrze wyjaśnił zespołowi nowe zasady haseł.", ["KOMUNIKACJA"], "positive", "manager"),
    ],
    "Katarzyna Wiśniewska": [
        (date(2025, 2, 18), "Uporządkowała katalog formularzy elektronicznych; usunęła 14 nieaktualnych wzorów.", ["RZETELNOSC"], "positive", "manager"),
        (date(2025, 8, 7), "Kilka odpowiedzi do użytkowników e-usług wysłała po terminie.", ["ORGANIZACJA_PRACY"], "negative", "manager"),
        (date(2025, 12, 3), "Przygotowała zestawienie danych o wykorzystaniu e-usług z trafnymi wnioskami.", ["WIEDZA", "KOMUNIKACJA"], "positive", "manager"),
        (date(2026, 4, 21), "Współpracowała z Wydziałem Obsługi Klienta przy nowej ankiecie satysfakcji.", ["WSPOLPRACA"], "positive", "manager"),
        (date(2026, 9, 9), "Terminowo wdrożyła 3 nowe formularze zgodne z wymaganiami dostępności.", ["RZETELNOSC", "ORGANIZACJA_PRACY"], "positive", "manager"),
    ],
    "Tomasz Wójcik": [
        (date(2025, 1, 30), "Przeprowadził wymianę przełączników sieciowych w weekend, bez przestoju w pracy urzędu.", ["ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2025, 4, 2), "Nie udokumentował zmian w konfiguracji zapory - trzeba było je odtwarzać.", ["RZETELNOSC"], "negative", "manager"),
    ],
    "Magdalena Kamińska": [
        (date(2025, 3, 25), "Zbudowała dashboard czasu załatwiania spraw; dyrekcja używa go na cotygodniowych odprawach.", ["WIEDZA", "ORGANIZACJA_PRACY"], "positive", "manager"),
        (date(2025, 9, 30), "Raport roczny zawierał błąd w danych za III kwartał - wykryty przez odbiorcę.", ["RZETELNOSC"], "negative", "manager"),
        (date(2026, 2, 11), "Przeszkoliła dwie osoby z innych wydziałów z obsługi narzędzia raportowego.", ["WSPOLPRACA"], "positive", "manager"),
        (date(2026, 7, 14), "Wprowadziła listę kontrolną jakości danych; kolejne raporty bez błędów.", ["RZETELNOSC"], "positive", "manager"),
    ],
}

# Wstępnie wypełnione oceny w bieżącym cyklu (demo kontroli jakości)
PIOTR_REVIEW = {
    "scores": {"WIEDZA": 9, "RZETELNOSC": 9, "ORGANIZACJA_PRACY": 9, "WSPOLPRACA": 9, "KOMUNIKACJA": 9},
    "justifications": {
        "RZETELNOSC": "Pracuje dobrze, bez zastrzeżeń.",
        "WSPOLPRACA": "Bardzo sympatyczny i młody, dobrze dogaduje się z zespołem.",
        "KOMUNIKACJA": "Wywiązuje się z obowiązków.",
    },
}

ANNA_SELF = {
    "scores": {"KOMUNIKACJA": (9, "Regularnie prezentuję wyniki projektów, wystąpiłam na konferencji wojewódzkiej."),
               "RZETELNOSC": (7, "Audyt bez uwag; raz opóźniłam dokumentację, z czego wyciągnęłam wnioski."),
               "ORGANIZACJA_PRACY": (9, "Utrzymałam terminy e-Doręczeń mimo odejścia osoby z zespołu."),
               "WSPOLPRACA": (7, "Wdrażałam nową osobę, pomagałam innym wydziałom."),
               "WIEDZA": (9, "Certyfikat ITIL, kurs cyberbezpieczeństwa, analiza nowelizacji KSC."),
               "KREATYWNOSC": (7, "Automatyzacja raportu i nowy formularz zgłoszeń awarii.")},
    "summary": "Chciałabym w kolejnym okresie rozwijać się w kierunku kierowania projektami IT.",
}

# --- proces oceny: dane do etapów (część I arkusza, nieobecności, historia) ---
OFFICE_CITY = "Przykładowo"

# nowe umowy na czas nieokreślony - pierwszy okres oceny zaczyna się od nawiązania stosunku pracy
NEW_HIRES = {"Jakub Lewandowski": date(2026, 11, 2)}

# poprzednia ocena Anny na poziomie „powyżej oczekiwań” - przy kolejnej takiej ocenie obligatoryjny stopień (art. 89 ust. 2)
PREV_FIXED = {"Anna Kowalska": 7}

MAGDA_ADDITIONAL = ("MYSLENIE_ANALITYCZNE",)

# zwolnienie lekarskie i urlop bez przerwy roboczej -> jedna nieobecność > 1 miesiąca (art. 81 ust. 7)
ABSENCES = {
    "Tomasz Wójcik": [
        (date(2025, 9, 1), date(2025, 9, 19), "zwolnienie lekarskie"),
        (date(2025, 9, 22), date(2025, 10, 17), "urlop wypoczynkowy"),
    ],
}

OPENING_NOTES = {
    "Anna Kowalska": "Omówiono obowiązki z opisu stanowiska i kryteria. Oczekiwania: samodzielne prowadzenie "
                     "wdrożenia EZD w 2 wydziałach, przygotowanie dokumentacji przetargu na serwis sieci, "
                     "jasna komunikacja z dyrekcją i interesariuszami. Cel rozwojowy: wystąpienia publiczne.",
    "Piotr Nowak": "Omówiono obowiązki i kryteria. Oczekiwania: terminowa obsługa incydentów, "
                   "plan odtwarzania kopii zapasowych, raport kwartalny z bezpieczeństwa.",
    "Tomasz Wójcik": "Omówiono obowiązki i kryteria. Oczekiwania: modernizacja serwerowni, dokumentacja infrastruktury.",
    "Magdalena Kamińska": "Omówiono obowiązki i kryteria (dodatkowo: myślenie analityczne). Oczekiwania: "
                          "nowy model raportowania zarządczego, automatyzacja raportów miesięcznych.",
}

# --- HR partner: sygnały do rozmowy o kondycji pracownika (dane fikcyjne) ---
NOTES["Katarzyna Wiśniewska"] = NOTES["Katarzyna Wiśniewska"] + [
    (date(2026, 9, 24), "Przejęła obsługę zgłoszeń e-usług po odejściu koleżanki - obecnie prowadzi dwa obszary jednocześnie.",
     ["ORGANIZACJA_PRACY"], "neutral", "manager"),
    (date(2026, 10, 14), "Kolejny tydzień zostaje po godzinach, żeby nadrobić zaległości w odpowiedziach do użytkowników.",
     ["ORGANIZACJA_PRACY"], "negative", "manager"),
    (date(2026, 10, 30), "Na spotkaniu zespołu była wycofana, nie zgłosiła uwag do nowego formularza, choć zwykle jest aktywna.",
     ["WSPOLPRACA", "KOMUNIKACJA"], "negative", "manager"),
    (date(2026, 11, 12), "Dwie odpowiedzi do użytkowników wysłane po terminie; sama powiedziała, że nie nadąża z liczbą zgłoszeń.",
     ["RZETELNOSC", "ORGANIZACJA_PRACY"], "negative", "manager"),
]
NOTES["Magdalena Kamińska"] = NOTES["Magdalena Kamińska"] + [
    (date(2026, 11, 10), "Zautomatyzowała raport miesięczny - oszczędność ok. 2 dni pracy zespołu w każdym miesiącu.",
     ["MYSLENIE_ANALITYCZNE", "ORGANIZACJA_PRACY"], "positive", "manager"),
]
