import pytest

from raya import calcul


@pytest.mark.parametrize("demande, attendu", [
    ("Combien font 15 % de 240 ?", ["15 % de 240 = 36"]),
    ("combien font 15% de 240", ["15 % de 240 = 36"]),
    ("12 fois 37", ["12 × 37 = 444"]),
    ("Calcule 245 divisé par 7", ["245 ÷ 7 = 35"]),
    ("12,5 x 4 = ?", ["12,5 × 4 = 50"]),
    ("combien font 3 plus 4 fois 2", ["3 + 4 × 2 = 11"]),
    ("combien font 7 moins 3", ["7 − 3 = 4"]),
    ("combien font (120 + 45) / 3", ["(120 + 45) ÷ 3 = 55"]),
    ("combien font 9 au carré", ["9 ^ 2 = 81"]),
    ("2 puissance 10", ["2 ^ 10 = 1 024"]),
    ("racine carrée de 2", ["racine carrée de 2 = 1,4142 (arrondi)"]),
    ("la moyenne de 12, 15 et 9", ["moyenne de 12, 15, 9 = 12"]),
    # En euros : deux décimales
    ("1 250 € moins 20 %", ["1 250 moins 20 % = 1 000 €"]),
    ("30 % de réduction sur 80 euros", ["80 moins 30 % = 56 €"]),
    ("un pull à 45 € avec 30 % de remise", ["45 moins 30 % = 31,50 €"]),
    ("partager 187,50 € entre 6", ["187,50 ÷ 6 = 31,25 €"]),
    ("3 fois 1,20 €", ["3 × 1,20 = 3,60 €"]),
    ("combien fait 10 divisé par 0", ["10 ÷ 0 : division par zéro impossible"]),
    # Phrases de tous les jours
    ("Ma fille a eu 12, 15,5 et 9 en maths, quelle est sa moyenne ?", ["moyenne de 12, 15,5, 9 = 12,1667 (arrondi)"]),
    ("Un loyer de 780 € augmente de 3,5 %, ça fait combien ?", ["780 plus 3,5 % = 807,30 €", "3,5 % de 780 = 27,30 €"]),
    ("le prix baisse de 20 % sur 50 €", ["50 moins 20 % = 40 €", "20 % de 50 = 10 €"]),
    ("On est 6 au restaurant, l'addition fait 187,50 €. Combien chacun doit payer ?", ["187,50 ÷ 6 = 31,25 €"]),
])
def test_calculs(demande, attendu):
    assert calcul.calculs(demande) == attendu


@pytest.mark.parametrize("demande", [
    "ouvre le fichier factures 2024 - 2025",  # pas de mot de calcul
    "rappelle-moi le 18/10/2026 à 15h",
    "combien de temps pour 15-20 minutes",  # une fourchette
    r"[Fichier joint : C:\x\2024-10 facture.pdf] fais le total",
    "combien font (2 + 3 fois 4",  # parenthèse non fermée : le modèle répond seul
    "combien font 2 puissance 1000",
    "qu'est-ce que tu fais ?",
])
def test_pas_de_calcul(demande):
    assert all("=" not in c for c in calcul.calculs(demande))


def test_bloc_du_prompt():
    assert calcul.bloc_calculs("Bonjour") == ""
    assert "- 15 % de 240 = 36" in calcul.bloc_calculs("15 % de 240")
