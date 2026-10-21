from datetime import datetime

import pytest

from dawaa import accueil
from dawaa.config import Reglages
from dawaa.stockage.memoire import Memoire


@pytest.fixture
def memoire(tmp_path):
    return Memoire(tmp_path / "test.sqlite")


@pytest.fixture
def reglages(monkeypatch):
    monkeypatch.setattr(Reglages, "enregistrer", lambda self: None)
    return Reglages()


def test_enregistrer_tout(reglages, memoire):
    assert accueil.enregistrer(reglages, memoire, " Michel ", "Michel.Durand@hotmail.fr", ["agenda", "emails", "pirate"]) is None
    assert (reglages.prenom, reglages.email, reglages.usages) == ("Michel", "michel.durand@hotmail.fr", ["agenda", "emails"])
    assert reglages.accueil_fait and reglages.messagerie == "outlook"
    souvenirs = [s["texte"] for s in memoire.souvenirs()]
    assert "Son prénom est Michel." in souvenirs
    assert "Utilise surtout Dawaa pour : agenda et rappels, préparer des e-mails." in souvenirs
    moi = [{"id": 1, "nom": "Moi (Michel)", "email": "michel.durand@hotmail.fr"}]
    assert memoire.trouver_contacts("moi") == moi and memoire.trouver_contacts("Michel") == moi


def test_tout_passer(reglages, memoire):
    assert accueil.enregistrer(reglages, memoire, "", "", []) is None
    assert reglages.accueil_fait and memoire.souvenirs() == [] and memoire.contacts() == []


def test_email_incorrect(reglages, memoire):
    assert "ne semble pas correcte" in accueil.enregistrer(reglages, memoire, "Michel", "michel", [])
    assert not reglages.accueil_fait and memoire.souvenirs() == []


def test_refaire_la_presentation(reglages, memoire):
    accueil.enregistrer(reglages, memoire, "Michel", "michel@gmail.com", ["excel"])
    accueil.enregistrer(reglages, memoire, "Michèle", "", ["excel", "internet"])
    souvenirs = [s["texte"] for s in memoire.souvenirs()]
    assert souvenirs.count("Son prénom est Michèle.") == 1 and "Son prénom est Michel." not in souvenirs
    assert len([s for s in souvenirs if s.startswith("Utilise surtout")]) == 1
    assert memoire.contacts() == []  # adresse retirée : le contact « Moi » aussi


def test_messagerie_selon_l_adresse():
    assert accueil.messagerie_pour("marie@gmail.com") == "gmail"
    assert accueil.messagerie_pour("marie@live.fr") == "outlook"
    assert accueil.messagerie_pour("marie@orange.fr") is None


def test_apercu_et_suggestions():
    ids = [f["id"] for f in accueil.apercu(["excel", "agenda"])]
    assert ids[:3] == ["voix", "agenda", "excel"] and ids[-4:] == ["memoire", "ecran", "calculs", "raccourcis"]
    assert len(ids) == len(set(ids)) == len(accueil.FONCTIONS) + len(accueil.FONCTIONS_DE_BASE)
    assert [s["titre"] for s in accueil.suggestions([])] == ["Écrire une lettre", "Faire un tableau Excel",
                                                             "Chercher sur internet"]
    assert [s["titre"] for s in accueil.suggestions(["agenda"])] == ["Noter un rendez-vous", "Écrire une lettre",
                                                                     "Faire un tableau Excel"]


def test_salutation():
    assert accueil.salutation("Michel", datetime(2026, 10, 21, 9, 5)) == (
        "Bonjour Michel, bienvenue ! Nous sommes le mercredi 21 octobre, et il est 9 heures 5. "
        "Que puis-je faire pour vous aujourd'hui ?")
    sans_prenom = accueil.salutation("", datetime(2026, 11, 1, 19, 0))
    assert sans_prenom.startswith("Bonsoir, bienvenue ! Nous sommes le dimanche 1er novembre, et il est 19 heures.")
    assert "il est 1 heure 30." in accueil.salutation("", datetime(2026, 11, 2, 1, 30))
