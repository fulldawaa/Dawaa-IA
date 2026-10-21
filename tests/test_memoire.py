import pytest

from dawaa import outils
from dawaa.app import elements_a_afficher
from dawaa.llm.agent import annonce_sans_outil, bloc_memoire
from dawaa.outils import navigation, souvenirs
from dawaa.stockage.historique import Historique
from dawaa.stockage.memoire import Memoire
from dawaa.stockage.sensible import masquer, raison_sensible


@pytest.fixture
def memoire(tmp_path):
    m = Memoire(tmp_path / "test.sqlite")
    souvenirs.configurer(m)
    navigation.configurer(m)
    navigation.contexte.derniere_demande = ""
    navigation.contexte.en_attente = ""
    return m


# ---------- informations sensibles ----------

@pytest.mark.parametrize("texte", [
    "Son mot de passe Gmail est soleil123",
    "Le code PIN de sa carte est 1234",
    "Sa carte bancaire : 4970 1012 3456 7893",  # numéro valide (Luhn)
    "Son IBAN est FR76 3000 6000 0112 3456 7890 189",
    "Son numéro de sécu est 1 85 05 78 006 084 36",
])
def test_infos_sensibles_refusees(memoire, texte):
    assert raison_sensible(texte)
    resultat = outils.executer("memoire", {"action": "retenir", "texte": texte})
    assert resultat.startswith("Refusé")
    assert memoire.souvenirs() == []


@pytest.mark.parametrize("texte", [
    "Sa fille s'appelle Léa", "Il habite au 12 rue des Lilas à Lyon", "Son numéro de client EDF est 4521",
    "Il est né en 1952", "Son médecin est le docteur Martin, tél 04 78 12 34 56",
])
def test_infos_ordinaires_acceptees(texte):
    assert raison_sensible(texte) is None


def test_masquer_les_longs_numeros():
    assert masquer("Carte 4970 1012 3456 7893 et IBAN FR76 3000 6000 0112 3456 7890 189") == "Carte [masqué] et IBAN [masqué]"


# ---------- souvenirs ----------

def test_retenir_puis_oublier(memoire):
    r = outils.executer("memoire", {"action": "retenir", "texte": "Sa fille s'appelle Léa"})
    assert r.startswith("Retenu [souvenir n°")
    assert memoire.souvenirs()[0]["texte"] == "Sa fille s'appelle Léa."
    assert "- Sa fille s'appelle Léa." in memoire.pour_prompt()
    assert outils.executer("memoire", {"action": "oublier", "texte": "le prénom de ma fille Léa"}).startswith("Oublié")
    assert memoire.souvenirs() == []
    assert "rien retenu" in outils.executer("memoire", {"action": "oublier", "texte": "mon chien"})


def test_souvenir_presque_identique_remplace(memoire):
    memoire.retenir("Il préfère des réponses courtes")
    _, remplace = memoire.retenir("Il préfère des réponses très courtes")
    assert remplace and len(memoire.souvenirs()) == 1


def test_affichage_sous_la_reponse(memoire):
    r = outils.executer("memoire", {"action": "retenir", "texte": "Il habite à Lyon"})
    elements = elements_a_afficher([{"role": "tool", "content": r}])
    assert elements["souvenirs"] == [{"id": memoire.souvenirs()[0]["id"], "texte": "Il habite à Lyon"}]


def test_bloc_memoire_dans_le_prompt():
    bloc = bloc_memoire("- Sa fille s'appelle Léa.", [(1792306890, "Il a écrit une lettre de résiliation.")])
    assert "Sa fille s'appelle Léa" in bloc and "lettre de résiliation" in bloc


def test_resumes_de_conversations(tmp_path):
    h = Historique(tmp_path / "h.sqlite")
    a = h.enregistrer(None, [{"role": "user", "content": "Bonjour"}])
    b = h.enregistrer(None, [{"role": "user", "content": "Météo ?"}])
    assert set(h.a_resumer(sauf=b)) == {a}
    h.definir_resume(a, "Il a dit bonjour.")
    assert h.a_resumer(sauf=b) == []
    assert h.resumes_recents() == [(pytest.approx(h.lister()[1]["modifiee"]), "Il a dit bonjour.")]
    h.enregistrer(a, [{"role": "user", "content": "Bonjour"}, {"role": "user", "content": "Encore"}])
    assert h.a_resumer(sauf=b) == [a]  # conversation reprise : résumé à refaire


def test_cinq_conversations_au_plus(tmp_path):
    chemin = tmp_path / "h.sqlite"
    h = Historique(chemin)
    ids = [h.enregistrer(None, [{"role": "user", "content": f"Question {i}"}]) for i in range(7)]
    assert [c["id"] for c in h.lister()] == ids[:1:-1]  # les 5 dernières, la plus récente en tête
    # Reprendre une ancienne conversation la garde : c'est la plus ancienne restante qui part ensuite
    h.enregistrer(ids[2], [{"role": "user", "content": "Question 2, suite"}])
    h.enregistrer(None, [{"role": "user", "content": "Question 7"}])
    assert ids[2] in [c["id"] for c in h.lister()] and ids[3] not in [c["id"] for c in h.lister()]
    assert h.charger(ids[0]) == []
    # Un historique plus ancien que la limite est réduit à l'ouverture
    import sqlite3, time
    db = sqlite3.connect(chemin)
    db.executemany("INSERT INTO conversations (titre, messages, modifiee) VALUES ('x', '[]', ?)",
                   [(time.time() + i,) for i in range(4)])
    db.commit()
    db.close()
    assert len(Historique(chemin).lister()) == 5


def test_garde_fou_memoire():
    assert annonce_sans_outil("Ma fille s'appelle Léa", "C'est noté ! J'ai bien retenu que votre fille s'appelle Léa.")
    assert annonce_sans_outil("Ouvre le site de ma mairie", "J'ai ouvert le site de la mairie pour vous.")
    assert not annonce_sans_outil("Quelle heure est-il ?", "Il est 15 h.")


# ---------- sites web ----------

@pytest.fixture
def ouverts(monkeypatch):
    liste = []
    monkeypatch.setattr(navigation, "_ouvrir", liste.append)
    return liste


@pytest.mark.parametrize("nom, attendu", [
    ("YouTube", "https://www.youtube.com"), ("le site de la CAF", "https://www.caf.fr"),
    ("La Poste", "https://www.laposte.fr"), ("impots.gouv.fr", "https://www.impots.gouv.fr"),
    ("Météo-France", "https://meteofrance.com"),
])
def test_sites_connus_ouverts_directement(memoire, ouverts, nom, attendu):
    assert "ouvert" in navigation.ouvrir_site(nom)
    assert ouverts == [attendu]


def test_recherche_directe(memoire, ouverts):
    navigation.ouvrir_site("YouTube", "recette de crêpes")
    navigation.ouvrir_site("Maps", "pharmacie Lyon")
    navigation.ouvrir_site("", "horaires piscine")
    assert ouverts == ["https://www.youtube.com/results?search_query=recette+de+cr%C3%AApes",
                       "https://www.google.com/maps/search/pharmacie+Lyon",
                       "https://www.google.fr/search?q=horaires+piscine"]


def test_favori(memoire, ouverts):
    memoire.ajouter_favori("Ma banque", "www.credit-agricole.fr")
    assert "favori" in navigation.ouvrir_site("ma banque")
    assert ouverts == ["https://www.credit-agricole.fr"]
    with pytest.raises(ValueError):
        memoire.ajouter_favori("Test", "pas une adresse")


def test_adresse_donnee_par_l_utilisateur(memoire, ouverts):
    navigation.contexte.derniere_demande = "Ouvre www.mairie-exemple.fr s'il te plaît"
    assert "ouvert" in navigation.ouvrir_site("mairie-exemple.fr")
    assert ouverts == ["https://mairie-exemple.fr"]


def test_site_trouve_par_recherche_demande_confirmation(memoire, ouverts, monkeypatch):
    class FauxDDGS:
        def text(self, *a, **k):
            return [{"title": "Mairie de Villeneuve", "href": "https://www.villeneuve.fr/"}]
    monkeypatch.setattr(navigation, "DDGS", FauxDDGS)
    navigation.contexte.derniere_demande = "Ouvre le site de la mairie de Villeneuve"
    r = navigation.ouvrir_site("mairie de Villeneuve")
    assert ouverts == [] and "PAS encore ouvert" in r
    assert elements_a_afficher([{"role": "tool", "content": r}])["propositions"] == [
        {"url": "https://www.villeneuve.fr/", "titre": "Mairie de Villeneuve", "domaine": "villeneuve.fr"}]
    # Le modèle ne peut pas ouvrir l'adresse de lui-même…
    assert "PAS encore ouvert" in navigation.ouvrir_site("https://www.villeneuve.fr/")
    # …mais oui, si l'utilisateur vient de confirmer
    navigation.contexte.derniere_demande = "Oui vas-y"
    assert "ouvert" in navigation.ouvrir_site("https://www.villeneuve.fr/")
    assert ouverts == ["https://www.villeneuve.fr/"]


@pytest.mark.parametrize("texte, attendu", [
    ("Sa fille s'appelle Léa et a 12 ans", ["Sa fille s'appelle Léa", "Sa fille a 12 ans"]),
    ("Son prénom est Michel et il habite à Lyon", ["Son prénom est Michel", "Il habite à Lyon"]),
    ("La fille de Michel s'appelle Léa et elle a 12 ans", ["La fille de Michel s'appelle Léa", "La fille de Michel a 12 ans"]),
    ("Il s'appelle Michel et habite à Lyon.", ["Il s'appelle Michel", "Il habite à Lyon"]),
    ("Il aime le jazz et le rock", ["Il aime le jazz et le rock"]),
    ("Son médecin est le docteur Martin", ["Son médecin est le docteur Martin"]),
])
def test_decoupage_des_souvenirs(texte, attendu):
    assert souvenirs.decouper(texte) == attendu


def test_oublier_une_partie_garde_le_reste(memoire):
    r = outils.executer("memoire", {"action": "retenir", "texte": "Il s'appelle Michel et habite à Lyon"})
    assert len(elements_a_afficher([{"role": "tool", "content": r}])["souvenirs"]) == 2
    outils.executer("memoire", {"action": "oublier", "texte": "il habite à Lyon"})
    assert [s["texte"] for s in memoire.souvenirs()] == ["Il s'appelle Michel."]
