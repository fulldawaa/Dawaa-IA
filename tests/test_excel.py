import re
from pathlib import Path

from openpyxl import load_workbook

from dawaa import outils
from dawaa.outils import excel


def _chemin(resultat: str) -> Path:
    return Path(re.search(r"ne pas montrer\) : (.+?\.xlsx)", resultat).group(1))


def _creer():
    return _chemin(excel.creer_tableau_excel(
        "Dépenses", ["Poste", "Montant", "Quantité"],
        [["Loyer", "650", 1], ["Courses", "320,50 €", 4], ["Essence", 80, 2]],
        ligne_total=True,
    ))


def test_creation_avec_total():
    chemin = _creer()
    ws = load_workbook(chemin).active
    assert [c.value for c in ws[1]] == ["Poste", "Montant", "Quantité"]
    assert ws["B3"].value == 320.5  # « 320,50 € » converti en nombre
    assert ws["A5"].value == "Total"
    assert ws["B5"].value == "=SUM(B2:B4)"
    assert ws["A1"].font.bold


def test_jamais_ecraser_a_la_creation():
    a, b = _creer(), _creer()
    assert a != b and a.exists() and b.exists()
    assert b.name == "Dépenses (2).xlsx"


def test_lecture_calcule_les_statistiques():
    texte = excel.lire_tableau_excel(str(_creer()))
    assert "3 ligne(s) de données" in texte
    assert "Montant : total = 1050.5" in texte
    assert "max = 650" in texte


def test_lecture_par_simple_nom():
    _creer()
    assert "Poste | Montant" in excel.lire_tableau_excel("Dépenses")


def test_modifications_sur_une_copie():
    original = _creer()
    resultat = excel.modifier_tableau_excel(str(original), [
        {"type": "ajouter_ligne", "valeurs": ["Internet", 30, 1]},
        {"type": "ajouter_colonne", "nom": "Coût total", "operation": "multiplier", "colonnes": ["Montant", "Quantité"]},
        {"type": "trier", "colonne": "montant", "ordre": "croissant"},
    ])
    copie = _chemin(resultat)
    assert copie.name == "Dépenses (modifié).xlsx"
    assert load_workbook(original).active.max_row == 5  # original intact
    ws = load_workbook(copie).active
    assert [ws.cell(row=r, column=1).value for r in range(2, 6)] == ["Internet", "Essence", "Courses", "Loyer"]
    assert ws["A6"].value == "Total" and ws["B6"].value == "=SUM(B2:B5)"
    # La formule a suivi sa ligne lors du tri
    assert ws["D1"].value == "Coût total" and ws["D2"].value == "=B2*C2" and ws["D5"].value == "=B5*C5"


def test_modification_successive_ne_ecrase_pas():
    original = _creer()
    c1 = _chemin(excel.modifier_tableau_excel(str(original), [{"type": "mettre_en_forme"}]))
    c2 = _chemin(excel.modifier_tableau_excel(str(c1), [{"type": "mettre_en_forme"}]))
    assert c2.name == "Dépenses (modifié 2).xlsx"


def test_colonne_inconnue_renvoie_un_message_clair():
    resultat = outils.executer("modifier_tableau_excel", {
        "chemin": str(_creer()), "actions": [{"type": "trier", "colonne": "Prix"}]})
    assert resultat.startswith("Erreur : Il n'y a pas de colonne « Prix »")
    assert "Montant" in resultat


def test_graphique():
    copie = _chemin(excel.ajouter_graphique_excel(str(_creer()), "barres", "Poste", ["Montant"], "Mes dépenses"))
    assert len(load_workbook(copie).active._charts) == 1


def test_fichier_absent():
    assert "Je ne trouve pas" in outils.executer("lire_tableau_excel", {"chemin": "inexistant.xlsx"})
