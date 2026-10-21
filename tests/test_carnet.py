import sqlite3

import pytest

from dawaa import accueil, outils
from dawaa.config import Reglages
from dawaa.llm.agent import numero_invente
from dawaa.outils import carnet, email, navigation
from dawaa.stockage.memoire import Memoire, numero_telephone


@pytest.fixture
def memoire(tmp_path):
    m = Memoire(tmp_path / "test.sqlite")
    email.configurer(m, lambda: "gmail")
    carnet.configurer(m)
    return m


def dire(phrase):
    navigation.contexte.derniere_demande = phrase


@pytest.mark.parametrize("texte, attendu", [
    ("06 12 34 56 78", "06 12 34 56 78"),
    ("son numéro c'est le 06.12.34.56.78", "06 12 34 56 78"),
    ("0612345678", "06 12 34 56 78"),
    ("06-12-34-56-78", "06 12 34 56 78"),
    ("+33 6 12 34 56 78", "06 12 34 56 78"),
    ("+33 (0)4 77 23 20 00", "04 77 23 20 00"),
    ("+44 20 7946 0958", "+44 20 7946 0958"),
    ("06 12 34", None),
    ("elle a 45 ans", None),
])
def test_formats_de_numero(texte, attendu):
    assert numero_telephone(texte) == attendu


def test_ancien_carnet_sans_telephone(tmp_path):
    chemin = tmp_path / "ancien.sqlite"
    db = sqlite3.connect(chemin)
    db.execute("CREATE TABLE contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, email TEXT NOT NULL)")
    db.execute("INSERT INTO contacts (nom, email) VALUES ('Nicole', 'nicole@gmail.com')")
    db.commit()
    db.close()
    assert Memoire(chemin).contacts() == [{"id": 1, "nom": "Nicole", "email": "nicole@gmail.com", "telephone": ""}]


def test_le_numero_complete_l_adresse(memoire):
    memoire.ajouter_contact("Nicole", "nicole@gmail.com")
    assert memoire.ajouter_contact("nicole", telephone="0612345678")[1] is True
    assert memoire.contacts() == [{"id": 1, "nom": "nicole", "email": "nicole@gmail.com", "telephone": "06 12 34 56 78"}]
    with pytest.raises(ValueError, match="numéro de téléphone"):
        memoire.ajouter_contact("Paul", telephone="12 34")
    with pytest.raises(ValueError, match="adresse e-mail ou un numéro"):
        memoire.ajouter_contact("Paul")


def test_enregistrer_un_numero_dit(memoire):
    dire("Enregistre le numéro de Nicole, c'est le 06 12 34 56 78")
    resultat = outils.executer("carnet", {"action": "ajouter", "nom": "Nicole", "telephone": "06 12 34 56 78"})
    assert "Contact enregistré : Nicole — 06 12 34 56 78" in resultat
    # Le modèle oublie de recopier le numéro : on le reprend dans la phrase de l'utilisateur
    dire("Note le numéro de Paul : 04.77.23.20.00")
    outils.executer("carnet", {"action": "ajouter", "nom": "Paul"})
    assert [(c["nom"], c["telephone"]) for c in memoire.contacts()] == [("Nicole", "06 12 34 56 78"),
                                                                       ("Paul", "04 77 23 20 00")]


def test_jamais_de_numero_invente(memoire):
    dire("Enregistre le numéro de Nicole")
    assert "donné lui-même" in outils.executer(
        "carnet", {"action": "ajouter", "nom": "Nicole", "telephone": "06 12 34 56 78"})
    dire("Le numéro de Nicole c'est le 06 12 34 56 78")
    assert "donné lui-même" in outils.executer(
        "carnet", {"action": "ajouter", "nom": "Nicole", "telephone": "06 12 34 56 79"})
    assert memoire.contacts() == []


def test_chercher(memoire):
    memoire.ajouter_contact("Nicole Martin", telephone="06 12 34 56 78")
    resultat = outils.executer("carnet", {"action": "chercher", "nom": "Nicole"})
    assert "Nicole Martin : téléphone 06 12 34 56 78, pas d'adresse e-mail" in resultat
    assert "n'est pas dans le carnet" in outils.executer("carnet", {"action": "chercher", "nom": "Paul"})
    memoire.ajouter_contact("Nicole Durand", "nd@gmail.com")
    assert "Plusieurs contacts" in outils.executer("carnet", {"action": "chercher", "nom": "Nicole"})
    # Le numéro lu dans le carnet n'est pas pris pour un numéro inventé
    messages = [{"role": "user", "content": "Quel est le numéro de Nicole Martin ?"},
                {"role": "tool", "tool_call_id": "1", "content": resultat}]
    assert not numero_invente("Le numéro de Nicole est le 06 12 34 56 78.", messages)


def test_memoire_renvoie_vers_le_carnet(memoire):
    from dawaa.outils import souvenirs
    souvenirs.configurer(memoire)
    resultat = outils.executer("memoire", {"action": "retenir", "texte": "Le numéro de sa fille est 06 12 34 56 78"})
    assert "carnet" in resultat and memoire.souvenirs() == []


def test_mail_a_un_contact_sans_adresse(memoire, monkeypatch):
    ouverts = []
    monkeypatch.setattr(navigation, "_ouvrir", ouverts.append)
    memoire.ajouter_contact("Nicole", telephone="06 12 34 56 78")
    dire("Envoie un mail à Nicole")
    assert "sans adresse e-mail" in outils.executer(
        "email", {"action": "preparer", "destinataire": "Nicole", "message": "Bonjour"})
    assert ouverts == []
    # L'adresse donnée dans la phrase complète le contact, sans perdre le numéro
    dire("Envoie un mail à Nicole, son adresse est nicole@gmail.com")
    outils.executer("email", {"action": "preparer", "destinataire": "Nicole", "message": "Bonjour"})
    assert len(ouverts) == 1
    assert memoire.contacts()[0] | {"id": 0} == {"id": 0, "nom": "Nicole", "email": "nicole@gmail.com",
                                                "telephone": "06 12 34 56 78"}


def test_accueil_garde_mon_numero(memoire, monkeypatch):
    monkeypatch.setattr(Reglages, "enregistrer", lambda self: None)
    reglages = Reglages()
    accueil.enregistrer(reglages, memoire, "Michel", "michel@gmail.com", [])
    memoire.ajouter_contact("Moi (Michel)", telephone="06 12 34 56 78")
    accueil.enregistrer(reglages, memoire, "Michel", "", [])
    assert [(c["nom"], c["email"], c["telephone"]) for c in memoire.contacts()] == [
        ("Moi (Michel)", "", "06 12 34 56 78")]
