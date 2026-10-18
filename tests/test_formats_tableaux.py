"""Tableaux .xls, .ods et .csv ; résumé d'un tableau qui ne commence pas en A1 ; fichiers ouverts à l'écran."""
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from dawaa import outils
from dawaa.llm.agent import CORRECTION_RECHERCHE, bloc_fichiers_ouverts, correction_necessaire
from dawaa.outils import excel, fichiers, ordinateur

EXEMPLES = Path(__file__).parent


@pytest.mark.parametrize("extension", [".xls", ".ods"])
def test_lire_xls_et_ods(extension):
    texte = excel.lire_tableau_excel(str(EXEMPLES / f"exemple_tableau{extension}"))
    assert "Titre : Bilan de l'entreprise" in texte
    assert "Colonnes : Groupe d'articles | Chiffre d'affaires | Charges | Date" in texte
    assert "Mobilier | 2000000 | 1240000 | 05/01/2026" in texte
    # La ligne Total du fichier n'est pas comptée deux fois
    assert "Chiffre d'affaires : total = 5250000" in texte
    assert "Ligne(s) de total déjà présentes dans le fichier : Total | 5250000" in texte
    assert "double : total = 42" in texte  # résultat des formules


def test_lire_csv_point_virgule(tmp_path):
    f = tmp_path / "comptes.csv"
    f.write_text("Poste;Montant\nLoyer;650,50\nCourses;120\n", encoding="cp1252")
    assert "Montant : total = 770.5" in excel.lire_tableau_excel(str(f))


def test_lire_une_feuille_precise():
    texte = excel.lire_tableau_excel(str(EXEMPLES / "exemple_tableau.ods"), feuille="formules")
    assert "Feuille « Formules »" in texte and "Feuille « Bilan »" not in texte
    assert "Il n'y a pas de feuille" in outils.executer(
        "lire_tableau_excel", {"chemin": str(EXEMPLES / "exemple_tableau.ods"), "feuille": "graphique"})


def test_xls_du_bureau(monkeypatch):
    bureau = fichiers.dossiers_personnels()["bureau"]
    shutil.copy(EXEMPLES / "exemple_tableau.xls", bureau / "EXOS BASES.xls")
    # Le mauvais outil renvoie vers le bon, avec le chemin
    assert "tableau Excel (outil lire_tableau_excel)" in outils.executer("lire_document", {"chemin": "exos bases"})
    assert "Chiffre d'affaires : total" in outils.executer("lire_tableau_excel", {"chemin": "EXOS BASES.xls"})
    # « Lis-moi le fichier » envoyé par erreur à ouvrir_fichier : il est lu
    monkeypatch.setattr(ordinateur.contexte, "derniere_demande", "Lis-moi le fichier exos bases")
    monkeypatch.setattr(ordinateur, "ouvrir", lambda _: pytest.fail("ne doit pas ouvrir"))
    assert "Chiffre d'affaires : total" in outils.executer("ouvrir_fichier", {"nom": "exos bases"})


def test_modifier_un_csv_cree_une_copie_xlsx(tmp_path):
    source = tmp_path / "comptes.csv"
    source.write_text("Poste;Montant\nLoyer;650\nCourses;120\n", encoding="utf-8")
    resultat = excel.ajouter_graphique_excel(str(source), "barres", "Poste", ["Montant"])
    copie = tmp_path / "comptes (modifié).xlsx"
    assert copie.is_file() and str(copie) in resultat
    assert load_workbook(copie).active["B2"].value == 650
    assert source.read_text(encoding="utf-8").startswith("Poste;Montant")  # original intact


def test_modifier_un_tableau_decale_explique_pourquoi(tmp_path):
    source = tmp_path / "ancien.xls"
    shutil.copy(EXEMPLES / "exemple_tableau.xls", source)
    resultat = outils.executer("ajouter_graphique_excel", {"chemin": str(source), "type": "barres",
                                                           "colonne_x": "Groupe d'articles", "colonnes_y": ["Charges"]})
    assert "ne commence pas tout en haut" in resultat


def test_texte_commencant_par_egal_reste_du_texte(tmp_path):
    f = tmp_path / "egal.csv"
    f.write_text("Nom;Note\n=moi;12\n", encoding="utf-8")
    wb = excel._classeur(f)
    assert wb.active["A2"].value == "=moi" and wb.active["A2"].data_type == "s"


def test_titres_de_fenetres():
    def nom(titre):
        m = ordinateur.TITRE_DOCUMENT.match(titre)
        return m and (ordinateur.MENTIONS_TITRE.sub("", m["nom"]).strip(), m["programme"])

    assert nom("EXOS BASES.xls — LibreOffice Calc") == ("EXOS BASES.xls", "LibreOffice Calc")
    assert nom("Budget [Mode de compatibilité] - Excel") == ("Budget", "Excel")
    assert nom("*notes.txt - Bloc-notes") == ("notes.txt", "Bloc-notes")
    assert nom("Facture.pdf - Adobe Acrobat Reader (64-bit)") == ("Facture.pdf", "Adobe Acrobat Reader (64-bit)")
    assert nom("Ma banque - Personnel - Microsoft Edge") is None  # pas les navigateurs
    assert isinstance(ordinateur.fichiers_ouverts(), list)


def test_fichiers_ouverts_dans_le_prompt():
    assert bloc_fichiers_ouverts([]) == ""
    assert "- EXOS BASES.xls (LibreOffice Calc)" in bloc_fichiers_ouverts(["EXOS BASES.xls (LibreOffice Calc)"])


def test_relance_si_le_modele_dit_ne_pas_avoir_acces():
    reponse = "Je ne peux pas lire directement le fichier Excel. Je n'ai pas accès à son contenu."
    assert correction_necessaire("Oui", reponse) == CORRECTION_RECHERCHE
    assert correction_necessaire("Ouvre Chrome", "Je ne peux pas ouvrir de programme.") is None
