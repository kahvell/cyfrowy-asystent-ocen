from app.ai.pseudonymizer import Pseudonymizer


def test_names_and_inflections_are_replaced_and_reverted():
    p = Pseudonymizer(["Anna Kowalska", "Piotr Nowak"])
    text = ("Anna Kowalska przygotowała raport. Pochwaliłem Annę za raport. Kowalskiej należy się uznanie. "
            "Piotr Nowak pomógł; Nowakowi dziękujemy. Kontakt: anna.k@urzad.gov.pl, tel. 600 100 200, PESEL 90010112345.")
    out = p.apply(text)
    for leak in ["Anna", "Annę", "Kowalsk", "Piotr", "Nowak", "anna.k@", "600 100 200", "90010112345"]:
        assert leak not in out, leak
    assert "[OSOBA_" in out and "[EMAIL]" in out and "[TELEFON]" in out and "[PESEL]" in out
    back = p.revert(out)
    assert "Anna Kowalska" in back and "Piotr Nowak" in back


def test_common_words_untouched():
    p = Pseudonymizer(["Piotr Nowak"])
    text = "Zaproponował nowe rozwiązanie i nowy formularz."
    assert p.apply(text) == text
