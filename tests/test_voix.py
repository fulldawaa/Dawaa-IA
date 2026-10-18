from dawaa.voix.tts import nettoyer_pour_voix


def test_nettoyage_markdown():
    texte = """## Résultat
Voici **le total** : 1 050 €.

| Poste | Montant |
|---|---|
| Loyer | 650 |

- premier point
Source : [Météo-France](https://meteofrance.com/) et https://exemple.fr/page
Fichier : C:\\Users\\moi\\Documents\\Dawaa\\Dépenses.xlsx"""
    propre = nettoyer_pour_voix(texte)
    assert "**" not in propre and "#" not in propre and "|" not in propre
    assert "Voici le total : 1 050 euros." in propre
    assert "Météo-France" in propre and "meteofrance.com" not in propre
    assert "le lien affiché" in propre
    assert "le fichier" in propre and "C:\\" not in propre
    assert "premier point" in propre and "- premier" not in propre
