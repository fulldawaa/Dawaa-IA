import pytest

from raya import outils
from raya.app import Application
from raya.llm.agent import bloc_memoire
from raya.outils import fichiers, navigation, ordinateur, souvenirs
from raya.stockage.memoire import Memoire


@pytest.fixture
def memoire(tmp_path):
    m = Memoire(tmp_path / "test.sqlite")
    souvenirs.configurer(m)
    navigation.configurer(m)
    return m


@pytest.fixture
def ouverts(monkeypatch):
    sites, fichiers_ouverts = [], []
    monkeypatch.setattr(navigation, "_ouvrir", sites.append)
    monkeypatch.setattr(ordinateur, "ouvrir", fichiers_ouverts.append)
    return sites, fichiers_ouverts


def faire(demande, outil, **arguments):
    """Comme l'application : la demande de l'utilisateur, puis l'appel d'outil du modèle."""
    navigation.contexte.derniere_demande = demande
    return outils.executer(outil, arguments)


def test_enregistrer_puis_rejouer(memoire, ouverts):
    sites, fichiers_ouverts = ouverts
    agenda = fichiers.dossiers_personnels()["bureau"] / "agenda.txt"
    agenda.write_text("Lundi : dentiste à 10 h", encoding="utf-8")
    faire("Ouvre la météo", "ouvrir_site", site="météo")
    faire("Lis-moi mon agenda sur le bureau", "ouvrir_fichier", nom="agenda", dossier="Bureau")
    resultat = faire("Retiens ça sous le nom ma routine du matin", "memoire",
                     action="enregistrer_raccourci", texte="Ma routine du matin")
    assert "1. Ouvrir météo\n2. Lire agenda" in resultat
    assert outils.journal == []

    sites.clear()
    resultat = faire("Fais ma routine du matin", "memoire", action="lancer_raccourci", texte="routine du matin")
    assert sites == ["https://meteofrance.com"]
    assert "dentiste à 10 h" in resultat  # « lis-moi » d'origine : le fichier est lu, pas seulement ouvert
    assert fichiers_ouverts == []
    assert navigation.contexte.derniere_demande == "Fais ma routine du matin"
    assert outils.journal == []  # un rejeu ne s'enregistre pas à nouveau


def test_seules_les_actions_reussies_et_sans_effet_sont_gardees(memoire, ouverts):
    faire("Crée une lettre", "creer_document_word", titre="Lettre", contenu="Bonjour")
    faire("Lis le contrat", "lire_document", chemin="contrat introuvable")
    faire("Ouvre YouTube", "ouvrir_site", site="YouTube")
    faire("Ouvre YouTube", "ouvrir_site", site="YouTube")  # doublon
    assert [a["outil"] for a in outils.journal] == ["ouvrir_site"]


def test_site_confirme_rejoue_sans_redemander(memoire, ouverts):
    sites, _ = ouverts
    faire("Ouvre www.mairie-exemple.fr", "ouvrir_site", site="www.mairie-exemple.fr")
    faire("Garde ça comme raccourci mairie", "memoire", action="enregistrer_raccourci", texte="mairie")
    sites.clear()
    faire("Lance le raccourci mairie", "memoire", action="lancer_raccourci", texte="mairie")
    assert sites == ["https://www.mairie-exemple.fr"]


def test_rien_a_enregistrer(memoire):
    assert "Aucune action à enregistrer" in faire("Retiens ça", "memoire", action="enregistrer_raccourci", texte="x")


def test_raccourci_inconnu_liste_les_existants(memoire, ouverts):
    faire("Ouvre YouTube", "ouvrir_site", site="YouTube")
    faire("Enregistre", "memoire", action="enregistrer_raccourci", texte="Mes vidéos")
    assert "« Mes vidéos »" in faire("Fais ma routine", "memoire", action="lancer_raccourci", texte="routine du soir")


def test_meme_nom_remplace_et_oublier_supprime(memoire, ouverts):
    faire("Ouvre YouTube", "ouvrir_site", site="YouTube")
    faire("Enregistre", "memoire", action="enregistrer_raccourci", texte="ma routine du matin")
    faire("Ouvre Gmail", "ouvrir_site", site="Gmail")
    assert "remplacé" in faire("Enregistre", "memoire", action="enregistrer_raccourci", texte="Routine du matin")
    (raccourci,) = memoire.raccourcis()
    assert [a["arguments"]["site"] for a in raccourci["actions"]] == ["Gmail"]
    assert "supprimé" in faire("Oublie ma routine du matin", "memoire", action="oublier", texte="ma routine du matin")
    assert memoire.raccourcis() == []


def test_raccourcis_dans_le_prompt_et_ma_memoire(memoire, ouverts, monkeypatch):
    faire("Ouvre YouTube et cherche des recettes", "ouvrir_site", site="YouTube", recherche="recettes")
    faire("Enregistre", "memoire", action="enregistrer_raccourci", texte="Recettes")
    assert "« Recettes »" in bloc_memoire("", [], ["Recettes"])
    app = Application.__new__(Application)
    app.memoire = memoire
    assert app.contenu_memoire()["raccourcis"][0]["actions"] == ["Ouvrir YouTube et chercher « recettes »"]
