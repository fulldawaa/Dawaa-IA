from urllib.parse import parse_qs, urlparse

import pytest

from dawaa import outils
from dawaa.app import Application
from dawaa.config import Reglages
from dawaa.llm.agent import CORRECTION_FICHIER, correction_necessaire
from dawaa.outils import email, navigation
from dawaa.stockage.memoire import Memoire


@pytest.fixture
def memoire(tmp_path):
    m = Memoire(tmp_path / "test.sqlite")
    email.configurer(m, lambda: "gmail")
    return m


@pytest.fixture
def ouverts(monkeypatch):
    liste = []
    monkeypatch.setattr(navigation, "_ouvrir", liste.append)
    return liste


def dire(phrase):
    navigation.contexte.derniere_demande = phrase


def champs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


@pytest.mark.parametrize("texte, attendu", [
    ("son adresse c'est nicole.martin@gmail.com", ["nicole.martin@gmail.com"]),
    ("nicole point martin arobase gmail point com", ["nicole.martin@gmail.com"]),
    ("jean tiret pierre arobase orange point fr.", ["jean-pierre@orange.fr"]),
    ("Nicole.Martin@Gmail.com et paul@free.fr", ["nicole.martin@gmail.com", "paul@free.fr"]),
    ("envoie un mail à Nicole", []),
])
def test_adresses_dites(texte, attendu):
    assert email.adresses_dites(texte) == attendu


def test_preparer_pour_un_contact(memoire, ouverts):
    memoire.ajouter_contact("Nicole Martin", "nicole.martin@gmail.com")
    dire("Envoie un mail à Nicole avec la date du restaurant")
    resultat = outils.executer("email", {"action": "preparer", "destinataire": "Nicole", "objet": "Restaurant",
                                         "message": "Bonjour Nicole,\n\nLe restaurant est samedi à 20 h.\n\nBises"})
    assert "PAS envoyé" in resultat and "Nicole Martin <nicole.martin@gmail.com>" in resultat
    (url,) = ouverts
    assert url.startswith("https://mail.google.com/mail/?view=cm")
    assert champs(url) == {"view": "cm", "fs": "1", "to": "nicole.martin@gmail.com", "su": "Restaurant",
                           "body": "Bonjour Nicole,\n\nLe restaurant est samedi à 20 h.\n\nBises"}


def test_outlook(memoire, ouverts):
    email.configurer(memoire, lambda: "outlook")
    memoire.ajouter_contact("Paul", "paul@free.fr")
    dire("Écris à Paul")
    outils.executer("email", {"action": "preparer", "destinataire": "Paul", "message": "Salut"})
    assert ouverts[0].startswith("https://outlook.live.com/mail/0/deeplink/compose?to=paul%40free.fr")


def test_jamais_d_adresse_inventee(memoire, ouverts):
    dire("Envoie un mail à Nicole")
    assert "n'est pas dans le carnet" in outils.executer(
        "email", {"action": "preparer", "destinataire": "Nicole", "message": "Bonjour"})
    assert "ne l'invente pas" in outils.executer(
        "email", {"action": "preparer", "destinataire": "nicole@gmail.com", "message": "Bonjour"})
    assert "donnée lui-même" in outils.executer(
        "email", {"action": "ajouter_contact", "nom": "Nicole", "adresse": "nicole@gmail.com"})
    assert ouverts == [] and memoire.contacts() == []


def test_adresse_dictee_enregistree(memoire, ouverts):
    dire("Son adresse c'est nicole point martin arobase gmail point com")
    resultat = outils.executer("email", {"action": "ajouter_contact", "nom": "Nicole",
                                         "adresse": "nicole.martin@gmail.com"})
    assert "Contact enregistré : Nicole — nicole.martin@gmail.com" in resultat
    # Adresse donnée dans la même phrase que la demande : contact ajouté au passage
    dire("Envoie un mail à Paul, son adresse est paul@free.fr, pour lui dire bonjour")
    assert "ajouté(e) au carnet" in outils.executer(
        "email", {"action": "preparer", "destinataire": "Paul", "message": "Bonjour Paul"})
    assert [c["nom"] for c in memoire.contacts()] == ["Nicole", "Paul"]


def test_homonymes(memoire, ouverts):
    memoire.ajouter_contact("Nicole Martin", "nm@gmail.com")
    memoire.ajouter_contact("Nicole Durand", "nd@gmail.com")
    dire("Écris à Nicole")
    assert "Plusieurs contacts" in outils.executer("email", {"action": "preparer", "destinataire": "Nicole",
                                                             "message": "Bonjour"})
    assert ouverts == []


def test_carnet(memoire):
    memoire.ajouter_contact("Nicole", "nicole@gmail.com")
    assert memoire.ajouter_contact("nicole", "Nicole.M@gmail.com")[1] is True  # même nom : mise à jour
    assert memoire.contacts() == [{"id": 1, "nom": "nicole", "email": "nicole.m@gmail.com"}]
    with pytest.raises(ValueError):
        memoire.ajouter_contact("Paul", "pas une adresse")
    memoire.supprimer_contact(1)
    assert memoire.contacts() == []


def test_mail_annonce_envoye_sans_outil():
    assert correction_necessaire("Envoie un mail à Nicole", "C'est fait, le mail est envoyé à Nicole.") == CORRECTION_FICHIER


def test_date_cherchee_dans_l_agenda():
    from dawaa.llm.agent import CORRECTION_AGENDA
    reponse = "J'ai besoin d'une information : quelle est la date du prochain restaurant ?"
    assert correction_necessaire("Envoie un mail à Nicole avec la date du prochain restaurant", reponse) == CORRECTION_AGENDA
    assert correction_necessaire("Rappelle-moi le dentiste", "À quelle heure est le dentiste ?") is None


def test_pas_de_signature_dawaa(memoire, ouverts):
    memoire.ajouter_contact("Paul", "paul@free.fr")
    dire("Écris à Paul")
    for signature in ("Dawaa", "Votre assistant", "Votre assistant Dawaa.", "[Votre prénom]"):
        ouverts.clear()
        outils.executer("email", {"action": "preparer", "destinataire": "Paul",
                                  "message": f"Bonjour Paul,\n\nÀ samedi !\n\nCordialement,\n{signature}"})
        assert champs(ouverts[0])["body"] == "Bonjour Paul,\n\nÀ samedi !\n\nCordialement,"


def test_reglage_messagerie(memoire, monkeypatch):
    app = Application.__new__(Application)
    app.reglages = Reglages()
    monkeypatch.setattr(Reglages, "enregistrer", lambda self: None)
    monkeypatch.setattr(app, "_lecteur", type("L", (), {"voix": ""})(), raising=False)
    assert app.modifier_reglages({"messagerie": "outlook"})["messagerie"] == "outlook"
    assert app.modifier_reglages({"messagerie": "yahoo"})["messagerie"] == "outlook"


def test_envoie_moi(memoire, ouverts):
    memoire.ajouter_contact("Moi (Michel)", "michel@gmail.com")
    for destinataire in ("moi", "Moi-même", "à moi", "Michel"):
        ouverts.clear()
        dire("Envoie-moi la liste de courses")
        outils.executer("email", {"action": "preparer", "destinataire": destinataire, "message": "Pain, lait"})
        assert champs(ouverts[0])["to"] == "michel@gmail.com"


def test_relance_si_texte_a_copier_coller():
    from dawaa.llm.agent import CORRECTION_EMAIL
    reponse = "Je ne peux pas envoyer de mail directement. Voici le projet de message à copier-coller :"
    assert correction_necessaire("Envoie-moi par mail la liste de courses", reponse) == CORRECTION_EMAIL
    assert correction_necessaire("Envoie-moi par mail la liste de courses",
                                 "Je vais le rédiger. Voulez-vous que j'ajoute autre chose ?") == CORRECTION_EMAIL
    assert correction_necessaire("Envoie un mail à Pierre", "Quelle est l'adresse e-mail de Pierre ?") is None
    assert correction_necessaire("Envoie un mail", "À qui dois-je l'envoyer ?") is None


def test_envoie_moi_ne_demande_pas_a_qui():
    from dawaa.llm.agent import CORRECTION_EMAIL
    assert correction_necessaire("Envoie-moi par mail la liste", "À qui voulez-vous l'envoyer ?") == CORRECTION_EMAIL
