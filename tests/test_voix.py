from raya.voix.tts import nettoyer_pour_voix


def test_nettoyage_markdown():
    texte = """## Résultat
Voici **le total** : 1 050 €.

| Poste | Montant |
|---|---|
| Loyer | 650 |

- premier point
Source : [Météo-France](https://meteofrance.com/) et https://exemple.fr/page
Fichier : C:\\Users\\moi\\Documents\\Raya\\Dépenses.xlsx"""
    propre = nettoyer_pour_voix(texte)
    assert "**" not in propre and "#" not in propre and "|" not in propre
    assert "Voici le total : 1 050 euros." in propre
    assert "Météo-France" in propre and "meteofrance.com" not in propre
    assert "le lien affiché" in propre
    assert "le fichier" in propre and "C:\\" not in propre
    assert "premier point" in propre and "- premier" not in propre


def test_efface_mal_entendu_corrige():
    from raya.voix.stt import corriger
    assert corriger("et face la première ligne.") == "Efface la première ligne."
    assert corriger("Et fesse-la.") == "Efface-la."
    assert corriger("Aie Faises Leu") == "Efface-le"
    assert corriger("et fasse") == "Efface"
    # « face » utilisé normalement : on ne touche à rien
    assert corriger("Et face à la mer, on est bien ?") == "Et face à la mer, on est bien ?"
    assert corriger("La maison fait face la mer") == "La maison fait face la mer"


def test_phrases_inventees_ignorees():
    from raya.voix.stt import corriger
    assert corriger("Sous-titres réalisés par la communauté Amara.org") == ""
    assert corriger("Merci d'avoir regardé cette vidéo !") == ""


def test_vocabulaire_avec_les_noms():
    from raya.voix.stt import VOCABULAIRE, vocabulaire
    assert vocabulaire() == VOCABULAIRE
    assert vocabulaire(["Michel", "", "Nicole Martin"]).endswith(" Noms : Michel, Nicole Martin.")
