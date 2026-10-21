import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from raya import dates, demarrage, outils
from raya.app import Application
from raya.config import Reglages
from raya.voix import alarme as alarme_module
from raya.outils import agenda as outil_agenda
from raya.stockage.agenda import Agenda

# Samedi 17 octobre 2026, 10 h
MAINTENANT = datetime(2026, 10, 17, 10, 0)


@pytest.fixture
def agenda(tmp_path):
    a = Agenda(tmp_path / "agenda.sqlite")
    outil_agenda.configurer(a)
    return a


# ---------- dates en français ----------

@pytest.mark.parametrize("texte, attendu", [
    ("mardi à 15h", datetime(2026, 10, 20, 15, 0)),
    ("mardi prochain à 15 h 30", datetime(2026, 10, 20, 15, 30)),
    ("demain matin", datetime(2026, 10, 18, 9, 0)),
    ("après-demain à midi", datetime(2026, 10, 19, 12, 0)),
    ("dans 20 minutes", datetime(2026, 10, 17, 10, 20)),
    ("dans une demi-heure", datetime(2026, 10, 17, 10, 30)),
    ("dans deux heures et demie", datetime(2026, 10, 17, 12, 30)),
    ("dans 2 semaines à 10h", datetime(2026, 10, 31, 10, 0)),
    ("le 3 novembre à 10h30", datetime(2026, 11, 3, 10, 30)),
    ("3/11 à 14h", datetime(2026, 11, 3, 14, 0)),
    ("le 1er janvier", datetime(2027, 1, 1, 9, 0)),  # déjà passé cette année : l'an prochain
    ("à 8h du soir", datetime(2026, 10, 17, 20, 0)),
    ("à 9h", datetime(2026, 10, 18, 9, 0)),  # 9 h est passé : demain
    ("huit heures et quart", datetime(2026, 10, 18, 8, 15)),
    ("à 7h moins le quart", datetime(2026, 10, 18, 6, 45)),
    ("vendredi soir", datetime(2026, 10, 23, 19, 0)),
    ("cet après-midi", datetime(2026, 10, 17, 14, 0)),
    ("tous les jours à 8h", datetime(2026, 10, 18, 8, 0)),
    ("tous les lundis à 10h", datetime(2026, 10, 19, 10, 0)),
])
def test_interpreter(texte, attendu):
    assert dates.interpreter(texte, MAINTENANT)[0] == attendu


@pytest.mark.parametrize("texte", ["la semaine prochaine", "un homme", "aujourd'hui à 8h", "le 31/02", "à 25h"])
def test_dates_refusees(texte):
    with pytest.raises(dates.DateIncomprise):
        dates.interpreter(texte, MAINTENANT)


def test_heure_par_defaut_signalee():
    assert dates.interpreter("demain", MAINTENANT) == (datetime(2026, 10, 18, 9, 0), False)
    assert dates.interpreter("demain à 15h", MAINTENANT)[1] is True


def test_repetitions():
    assert dates.repetition_dans("tous les jours à 8h") == "jour"
    assert dates.repetition_dans("chaque lundi") == "semaine"
    assert dates.repetition_dans("tous les mois le 5") == "mois"
    assert dates.repetition_dans("mardi à 15h") == ""
    debut = datetime(2026, 1, 31, 8)
    assert [dates.occurrence(debut, "mois", n).day for n in range(4)] == [31, 28, 31, 30]
    assert dates.prochaine(datetime(2026, 1, 1, 8), "jour", MAINTENANT) == datetime(2026, 10, 18, 8)


def test_decrire():
    assert dates.decrire(datetime(2026, 10, 20, 15, 0), MAINTENANT) == "mardi 20 octobre à 15 h"
    assert dates.decrire(datetime(2026, 10, 18, 8, 5), MAINTENANT) == "demain (dimanche 18 octobre) à 8 h 05"
    assert dates.decrire(datetime(2027, 1, 1, 12, 0), MAINTENANT) == "vendredi 1er janvier 2027 à midi"


# ---------- minuteurs ----------

@pytest.mark.parametrize("texte, attendu", [
    ("minuteur de 10 minutes", timedelta(minutes=10)),
    ("10 minutes", timedelta(minutes=10)),
    ("dans 20 minutes pour le gâteau", timedelta(minutes=20)),
    ("minuteur 1h30", timedelta(hours=1, minutes=30)),
    ("dans une heure et 10 minutes", timedelta(hours=1, minutes=10)),
    ("un quart d'heure", timedelta(minutes=15)),
    ("demi-heure", timedelta(minutes=30)),  # le modèle retire parfois « une »
    ("trois quarts d'heure", timedelta(minutes=45)),
    ("2 min 30", timedelta(minutes=2, seconds=30)),
    ("30 secondes", timedelta(seconds=30)),
    ("minuteur de 5 min s'il te plaît", timedelta(minutes=5)),
    # Des heures de la journée, pas des durées
    ("15 h", None), ("8 heures", None), ("à 8 heures", None), ("1h30", None), ("mardi à 15 h 30", None),
    ("dans 2 semaines à 10h", None), ("dans 3 jours", None),
])
def test_duree(texte, attendu):
    assert dates.duree(texte) == attendu


def test_minuteur_a_la_seconde():
    """Un minuteur lancé à 10 h 00 min 40 s sonne 10 minutes plus tard, pas 40 secondes trop tôt."""
    assert dates.interpreter("10 minutes", MAINTENANT.replace(second=40)) == (datetime(2026, 10, 17, 10, 10, 40), True)
    assert dates.decrire_duree(timedelta(hours=1, minutes=1, seconds=5)) == "1 heure 1 minute 5 secondes"


def test_outil_minuteur(agenda):
    resultat = outils.executer("agenda", {"action": "ajouter", "titre": "minuteur", "quand": "minuteur de 10 minutes"})
    assert resultat.startswith("Minuteur lancé : il sonnera dans 10 minutes, à ")
    (r,) = agenda.a_venir()
    assert r["titre"] == "Minuteur de 10 minutes"
    assert abs(r["quand"] - datetime.now() - timedelta(minutes=10)) < timedelta(seconds=5)
    # Sans titre aussi ; un titre parlant est gardé
    outils.executer("agenda", {"action": "ajouter", "quand": "30 secondes"})
    outils.executer("agenda", {"action": "ajouter", "titre": "Pâtes", "quand": "dans 9 minutes"})
    assert [r["titre"] for r in agenda.a_venir()] == ["Minuteur de 30 secondes", "Pâtes", "Minuteur de 10 minutes"]
    # Le temps restant est donné quand on demande
    liste = outils.executer("agenda", {"action": "lister", "periode": "aujourd'hui"})
    assert "(dans 10 minutes) : Minuteur de 10 minutes" in liste
    # Et le modèle l'a sous les yeux sans appeler d'outil
    assert re.search(r"\(dans (29|30) secondes\) : Minuteur de 30 secondes", outil_agenda.bloc_minuteurs())
    assert "Supprimé" in outils.executer("agenda", {"action": "supprimer", "titre": "le minuteur de 10 minutes"})


def test_annonce_fin_de_minuteur(agenda):
    app = Application.__new__(Application)
    app.agenda, app.fenetre, app._lecteur = agenda, FausseFenetre(), FauxLecteur()
    app.alarme, app.reglages, app.notifier_windows = FausseAlarme(), Reglages(), None
    agenda.ajouter("Minuteur de 10 minutes", MAINTENANT)
    assert app.verifier_rappels(MAINTENANT) == ["Minuteur de 10 minutes : c'est terminé !"]


def test_minuteur_annonce_sans_outil():
    from raya.llm.agent import CORRECTION_RAPPEL, correction_necessaire
    assert correction_necessaire("Mets un minuteur de 10 minutes", "C'est lancé ! Le minuteur sonnera dans 10 minutes.")         == CORRECTION_RAPPEL
    assert correction_necessaire("Rappelle-moi le pain demain", "D'accord, c'est noté pour demain.") == CORRECTION_RAPPEL
    assert correction_necessaire("Mets un minuteur", "Pour combien de temps ?") is None


# ---------- stockage et rappels ----------

def test_rappel_unique(agenda):
    r = agenda.ajouter("Dentiste", MAINTENANT + timedelta(hours=2), avance=60)
    assert agenda.rappels_dus(MAINTENANT) == []
    (du,) = agenda.rappels_dus(MAINTENANT + timedelta(hours=1))
    assert du["id"] == r["id"] and not du["manque"]
    agenda.marquer_rappele(du, MAINTENANT + timedelta(hours=1))
    assert agenda.rappels_dus(MAINTENANT + timedelta(hours=1, minutes=1)) == []
    # Rappelé une heure avant, mais toujours à venir dans l'agenda
    assert [x["titre"] for x in agenda.a_venir(MAINTENANT + timedelta(hours=1))] == ["Dentiste"]


def test_rappel_repete_saute_les_jours_manques(agenda):
    agenda.ajouter("Médicaments", datetime(2026, 10, 10, 8, 0), "jour")
    (du,) = agenda.rappels_dus(MAINTENANT)
    assert du["manque"]  # Raya était fermée
    agenda.marquer_rappele(du, MAINTENANT)
    assert agenda.a_venir(MAINTENANT)[0]["quand"] == datetime(2026, 10, 18, 8, 0)


def test_trouver_et_supprimer(agenda):
    agenda.ajouter("Rendez-vous chez le dentiste", datetime.now() + timedelta(days=1))
    r = agenda.trouver("le dentiste")
    agenda.supprimer(r["id"])
    assert agenda.a_venir() == []


# ---------- outil agenda ----------

def test_outil_ajouter_lister_supprimer(agenda):
    resultat = outils.executer("agenda", {"action": "ajouter", "titre": "Dentiste", "quand": "demain à 15h"})
    assert "Ajouté à l'agenda : demain (" in resultat and "à 15 h : Dentiste" in resultat
    assert "Répète à l'utilisateur exactement cette date" in resultat
    # Pas de doublon si le modèle appelle deux fois
    outils.executer("agenda", {"action": "ajouter", "titre": "Dentiste", "quand": "demain à 15h"})
    assert len(agenda.a_venir()) == 1
    assert "Dentiste" in outils.executer("agenda", {"action": "lister", "periode": "demain"})
    assert "Rien de prévu aujourd'hui" in outils.executer("agenda", {"action": "lister", "periode": "aujourd'hui"})
    assert "Supprimé" in outils.executer("agenda", {"action": "supprimer", "titre": "dentiste"})
    assert agenda.a_venir() == []


def test_outil_repetition_et_rappel_avant(agenda):
    resultat = outils.executer("agenda", {"action": "ajouter", "titre": "Médicaments", "quand": "tous les jours à 8h",
                                          "rappel_avant": "1 heure"})
    assert "(chaque jour)" in resultat and "Rappel 1 heure avant" in resultat
    (r,) = agenda.a_venir()
    assert r["repetition"] == "jour" and r["avance"] == 60
    # Sur une semaine : une seule ligne « tous les jours », pas sept
    semaine = outils.executer("agenda", {"action": "lister", "periode": "semaine"})
    assert semaine.count("Médicaments") == 1 and "- tous les jours à 8 h : Médicaments" in semaine
    assert outils.executer("agenda", {"action": "lister", "periode": "demain"}).count("Médicaments") == 1


def test_rappel_avant_impossible_ignore(agenda):
    """« Dans 20 minutes » avec « rappel 20 minutes avant » sonnerait tout de suite."""
    outils.executer("agenda", {"action": "ajouter", "titre": "Appeler ma fille", "quand": "dans 20 minutes",
                               "rappel_avant": 20})
    assert agenda.a_venir()[0]["avance"] == 0


def test_rappelle_moi_ajoute_au_lieu_de_lister(agenda, monkeypatch):
    from raya.outils import navigation
    monkeypatch.setattr(navigation.contexte, "derniere_demande", "Rappelle-moi le dentiste mardi à 15 h.")
    assert "AJOUTER" in outils.executer("agenda", {"action": "lister", "periode": "demain"})
    monkeypatch.setattr(navigation.contexte, "derniere_demande", "Rappelle-moi ce que j'ai demain")
    assert "Rien de prévu" in outils.executer("agenda", {"action": "lister", "periode": "demain"})


def test_outil_explique_les_erreurs(agenda):
    assert "pas assez précis" in outils.executer("agenda", {"action": "ajouter", "titre": "X", "quand": "la semaine prochaine"})
    assert "heure n'a été donnée" not in outils.executer("agenda", {"action": "ajouter", "titre": "Appeler maman",
                                                                     "quand": "demain"})
    assert "n'a pas donné d'heure" in outils.executer("agenda", {"action": "ajouter", "titre": "Pain",
                                                                  "quand": "après-demain"})
    assert "Je ne trouve pas" in outils.executer("agenda", {"action": "supprimer", "titre": "piscine"})


# ---------- annonces de l'application ----------

class FauxLecteur:
    def __init__(self):
        self.dits = []

    def dire(self, texte):
        self.dits.append(texte)


class FausseAlarme:
    def __init__(self):
        self.sons, self.suite = [], None

    def sonner(self, son, ensuite):
        self.sons.append(son)
        self.suite = ensuite  # comme si l'alarme sonnait encore


class FausseFenetre:
    def __init__(self):
        self.au_premier_plan = []
        self.affichee = False

    def show(self):
        self.affichee = True

    def restore(self):
        pass

    @property
    def on_top(self):
        return self.au_premier_plan[-1] if self.au_premier_plan else False

    @on_top.setter
    def on_top(self, valeur):
        self.au_premier_plan.append(valeur)

    def evaluate_js(self, _):
        pass

    run_js = evaluate_js


def test_annonces(agenda):
    app = Application.__new__(Application)
    app.agenda, app.fenetre, app._lecteur = agenda, FausseFenetre(), FauxLecteur()
    app.alarme, app.reglages = FausseAlarme(), Reglages(son_alarme="Alarm03")
    bulles = []
    app.notifier_windows = lambda texte, titre: bulles.append(texte)
    agenda.ajouter("Prendre les médicaments", MAINTENANT + timedelta(minutes=1))
    agenda.ajouter("Dentiste", MAINTENANT + timedelta(hours=1), avance=60)
    agenda.ajouter("Pharmacie", MAINTENANT - timedelta(days=1))
    annonces = app.verifier_rappels(MAINTENANT + timedelta(minutes=1))
    assert annonces == ["C'est l'heure : Prendre les médicaments.",
                        "Rappel : Dentiste, aujourd'hui (samedi 17 octobre) à 11 h.",
                        "Rappel manqué pendant que Raya était fermée : Pharmacie (vendredi 16 octobre à 10 h)."]
    assert bulles == annonces
    # Une seule alarme pour les trois rappels, fenêtre affichée par-dessus les autres programmes…
    assert app.alarme.sons == ["Alarm03"] and app.fenetre.affichee and app.fenetre.on_top
    assert app._lecteur.dits == []  # …et la voix attend la fin de l'alarme
    app.alarme.suite()  # « J'ai compris »
    assert app._lecteur.dits == [" ".join(annonces)] and not app.fenetre.on_top
    assert app.verifier_rappels(MAINTENANT + timedelta(minutes=2)) == []  # une seule fois


# ---------- alarme ----------

class FauxWinsound:
    SND_FILENAME, SND_ASYNC, SND_LOOP = 1, 2, 4

    def __init__(self):
        self.joues = []

    def PlaySound(self, son, drapeaux):
        self.joues.append((son and Path(son).stem, drapeaux))


@pytest.fixture
def faux_winsound(monkeypatch):
    faux = FauxWinsound()
    monkeypatch.setattr(alarme_module, "winsound", faux)
    return faux


def test_alarme_en_boucle_jusqu_a_j_ai_compris(faux_winsound):
    fini = threading.Event()
    a = alarme_module.Alarme()
    a.sonner("Alarm01", fini.set, duree_max=5)
    assert faux_winsound.joues == [("Alarm01", 1 | 2 | 4)] and not fini.is_set()  # en boucle
    a.arreter()
    assert fini.wait(2)
    assert faux_winsound.joues[-1] == (None, 0)  # son coupé


def test_alarme_s_arrete_seule_apres_le_delai(faux_winsound):
    fini = threading.Event()
    alarme_module.Alarme().sonner("Alarm02", fini.set, duree_max=0.1)
    assert fini.wait(2) and faux_winsound.joues[-1] == (None, 0)


def test_pas_de_sonnerie(faux_winsound):
    appels = []
    alarme_module.Alarme().sonner("", lambda: appels.append("voix"))
    alarme_module.Alarme().sonner("Inconnu", lambda: appels.append("voix"))
    assert appels == ["voix", "voix"] and faux_winsound.joues == []


def test_sons_d_alarme_de_windows_presents():
    assert alarme_module.chemin_son(alarme_module.SON_DEFAUT) is not None


# ---------- démarrage avec Windows ----------

def test_demarrage_ignore_en_developpement(monkeypatch):
    ecrit = []
    monkeypatch.setattr(demarrage.winreg, "SetValueEx", lambda *a: ecrit.append(a))
    demarrage.appliquer(True)
    assert demarrage.commande() is None and ecrit == []


def test_demarrage_inscrit_l_exe(monkeypatch):
    ecrit, efface = [], []
    monkeypatch.setattr(demarrage.sys, "frozen", True, raising=False)
    monkeypatch.setattr(demarrage.sys, "executable", r"C:\Programmes\Raya\Raya.exe")
    monkeypatch.setattr(demarrage.winreg, "SetValueEx", lambda cle, nom, _, type_, valeur: ecrit.append((nom, valeur)))
    monkeypatch.setattr(demarrage.winreg, "DeleteValue", lambda cle, nom: efface.append(nom))
    demarrage.appliquer(True)
    demarrage.appliquer(False)
    assert ecrit == [("Raya", r'"C:\Programmes\Raya\Raya.exe" --demarrage')] and efface == ["Raya"]
