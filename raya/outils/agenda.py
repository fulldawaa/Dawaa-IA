"""Outil « agenda » : ajouter, lister et supprimer des rendez-vous et des rappels.

Le modèle recopie le moment tel que l'utilisateur l'a dit (« mardi à 15 h ») ; la date est calculée en Python.
"""
import re
from datetime import datetime, timedelta

from raya import dates
from raya.outils.fichiers import ErreurOutil
from raya.outils.navigation import contexte
from raya.stockage.agenda import Agenda

MAX_LISTE = 15
RESTE_AFFICHE = timedelta(hours=3)
DEMANDE_AJOUT = re.compile(r"^\s*(rappelle[- ]moi|rappelez[- ]moi|note|notez|ajoute|ajoutez|mets|mettez|enregistre)\b"
                           r"(?!.*\b(ce que|qu'est-ce|quoi|quels?|quelles?)\b)", re.I)
SYNONYMES_REPETITION = {
    "jour": "jour", "jours": "jour", "quotidien": "jour", "quotidienne": "jour", "chaque jour": "jour",
    "semaine": "semaine", "hebdomadaire": "semaine", "chaque semaine": "semaine",
    "mois": "mois", "mensuel": "mois", "mensuelle": "mois", "chaque mois": "mois",
    "an": "an", "annee": "an", "année": "an", "annuel": "an", "annuelle": "an", "chaque année": "an",
}

_agenda: Agenda | None = None


def configurer(agenda_: Agenda) -> None:
    global _agenda
    _agenda = agenda_


def _minutes(valeur) -> int:
    """« 60 », 60, « 1 heure », « 2 jours » → minutes."""
    if isinstance(valeur, (int, float)):
        return max(0, int(valeur))
    texte = str(valeur or "").lower()
    if not (m := re.search(r"\d+", texte)):
        return 60 if "heure" in texte else 0
    n = int(m.group())
    return n * 1440 if "jour" in texte else n * 60 if "heure" in texte or re.search(r"\d\s*h\b", texte) else n


def decrire_rendez_vous(r: dict, maintenant: datetime | None = None) -> str:
    if r.get("tous_les_jours"):
        return f"tous les jours à {dates.decrire(r['quand'], maintenant).rsplit(' à ', 1)[1]} : {r['titre']}"
    texte = f"{dates.decrire(r['quand'], maintenant)}{_reste(r['quand'], maintenant)} : {r['titre']}"
    if r["repetition"]:
        texte += f" ({dates.REPETITIONS[r['repetition']]})"
    return texte


def _reste(quand: datetime, maintenant: datetime | None = None) -> str:
    """« (dans 7 minutes) » pour ce qui sonne dans moins de 3 heures (minuteurs surtout)."""
    reste = quand - (maintenant or datetime.now())
    if not timedelta() < reste <= RESTE_AFFICHE:
        return ""
    if reste >= timedelta(minutes=5):  # au-delà de 5 minutes, les secondes n'intéressent personne
        reste = timedelta(minutes=round(reste.total_seconds() / 60))
    return f" (dans {dates.decrire_duree(reste)})"


def bloc_minuteurs() -> str:
    """Partie du prompt avec ce qui sonne bientôt : « il reste combien de temps ? » se répond sans outil ni calcul."""
    if _agenda is None:
        return ""
    maintenant = datetime.now()
    proches = _agenda.a_venir(maintenant, maintenant + RESTE_AFFICHE)
    if not proches:
        return ""
    return ("\n\nMinuteurs et rappels des 3 prochaines heures (temps restant calculé à l'instant par le programme, "
            "à répéter tel quel) :\n" + "\n".join(f"- {decrire_rendez_vous(r, maintenant)}" for r in proches))


def _duree(minutes: int) -> str:
    if minutes % 1440 == 0:
        return f"{minutes // 1440} jour" + ("s" if minutes >= 2880 else "")
    if minutes % 60 == 0:
        return f"{minutes // 60} heure" + ("s" if minutes >= 120 else "")
    return f"{minutes} minutes"


def agenda(action: str, titre: str = "", quand: str = "", repetition: str = "", rappel_avant=0, periode: str = "") -> str:
    if _agenda is None:
        raise ErreurOutil("L'agenda n'est pas disponible.")
    action = (action or "").lower()
    if action.startswith("ajout"):
        return _ajouter(titre, quand, repetition, rappel_avant)
    if action.startswith(("list", "voir", "lire")):
        # « Rappelle-moi le dentiste mardi » : le modèle consulte parfois l'agenda au lieu d'ajouter
        if DEMANDE_AJOUT.search(contexte.derniere_demande):
            raise ErreurOutil("L'utilisateur demande d'AJOUTER un rappel, pas de consulter l'agenda. Appelle "
                              "maintenant agenda avec action=ajouter, un titre court et quand = ses mots exacts.")
        return _lister(periode)
    if action.startswith(("suppr", "effac", "annul")):
        return _supprimer(titre)
    raise ErreurOutil("Action inconnue : utilise « ajouter », « lister » ou « supprimer ».")


def _ajouter(titre: str, quand: str, repetition: str, rappel_avant) -> str:
    titre = (titre or "").strip().rstrip(".")
    if not (quand or "").strip():
        raise ErreurOutil("Indique quand : demande à l'utilisateur le jour et l'heure.")
    minuteur = dates.duree(quand)
    if minuteur and (not titre or dates.MINUTEUR.search(dates._simplifier(titre))):
        titre = f"Minuteur de {dates.decrire_duree(minuteur)}"
    if not titre:
        raise ErreurOutil("Indique ce qu'il faut noter (par exemple « Dentiste »).")
    try:
        moment, heure_donnee = dates.interpreter(quand)
    except dates.DateIncomprise as e:
        raise ErreurOutil(f"{e} Rien n'a été ajouté.") from None
    rep = SYNONYMES_REPETITION.get((repetition or "").strip().lower(), "") or dates.repetition_dans(quand)
    avance = _minutes(rappel_avant)
    if moment - timedelta(minutes=avance) <= datetime.now():
        avance = 0  # « dans 20 minutes » avec « rappel 20 minutes avant » sonnerait tout de suite
    # Le modèle appelle parfois l'outil deux fois de suite : pas de doublon (à la minute près, pour les minuteurs)
    deja = next((r for r in _agenda.a_venir() if r["titre"].lower() == titre.lower()
                 and abs(r["quand"] - moment) < timedelta(minutes=1)), None)
    r = deja or _agenda.ajouter(titre, moment, rep, avance)
    phrase = decrire_rendez_vous(r)
    if minuteur and not rep:
        return (f"Minuteur lancé : il sonnera dans {dates.decrire_duree(minuteur)}, "
                f"à {dates.decrire(r['quand']).rsplit(' à ', 1)[1]}. Dis-le à l'utilisateur en une phrase courte. "
                "Il entendra l'alarme, et peut l'arrêter en disant « annule le minuteur ».")
    resultat = f"Ajouté à l'agenda : {phrase}."
    if avance:
        resultat += f" Rappel {_duree(avance)} avant."
    if not heure_donnee:
        resultat += (f" L'utilisateur n'a pas donné d'heure : le rappel est à {dates.decrire(moment).rsplit(' à ', 1)[1]}. "
                     "Dis-le-lui et propose de changer l'heure.")
    return resultat + (f"\nRépète à l'utilisateur exactement cette date, pour qu'il puisse la vérifier : « {phrase} ». "
                       "Il sera prévenu à l'heure du rappel par une notification et à voix haute, si Raya est ouverte "
                       "ou dans la barre près de l'horloge.")


def _lister(periode: str) -> str:
    maintenant = datetime.now()
    debut_jour = maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    p = dates._simplifier(periode or "")
    if "apres-demain" in p:
        bornes, nom = (debut_jour + timedelta(days=2), debut_jour + timedelta(days=3)), "après-demain"
    elif "demain" in p:
        bornes, nom = (debut_jour + timedelta(days=1), debut_jour + timedelta(days=2)), "demain"
    elif "aujourd" in p or "jour" == p:
        bornes, nom = (maintenant, debut_jour + timedelta(days=1)), "aujourd'hui"
    elif "semaine" in p:
        bornes, nom = (maintenant, debut_jour + timedelta(days=7)), "dans les 7 prochains jours"
    elif "mois" in p:
        bornes, nom = (maintenant, debut_jour + timedelta(days=31)), "dans les 31 prochains jours"
    else:
        bornes, nom = (maintenant, None), "à venir"
    # Les rendez-vous répétés n'ont qu'une date enregistrée : on calcule leurs répétitions dans la période
    lignes = []
    plusieurs_jours = bornes[1] is None or bornes[1] - bornes[0] > timedelta(days=2)
    for r in _agenda.a_venir():
        d = r["quand"]
        if r["repetition"] == "jour" and plusieurs_jours:  # une ligne « tous les jours » plutôt que 7 ou 31
            lignes.append({**r, "tous_les_jours": True})
            continue
        while bornes[1] is None or d < bornes[1]:
            if d >= bornes[0]:
                lignes.append({**r, "quand": d})
            if not r["repetition"] or bornes[1] is None:  # sans limite de période : seulement la prochaine fois
                break
            d = dates.prochaine(r["debut"], r["repetition"], d)
    lignes.sort(key=lambda r: (not r.get("tous_les_jours"), r["quand"]))
    if not lignes:
        return f"Rien de prévu {nom} dans l'agenda."
    plus = f"\n(et {len(lignes) - MAX_LISTE} autres)" if len(lignes) > MAX_LISTE else ""
    return (f"Agenda {nom} (dates calculées par le programme, à répéter telles quelles) :\n"
            + "\n".join(f"- {decrire_rendez_vous(r, maintenant)}" for r in lignes[:MAX_LISTE]) + plus)


def _supprimer(titre: str) -> str:
    if not (titre or "").strip():
        raise ErreurOutil("Indique quel rendez-vous supprimer.")
    r = _agenda.trouver(titre)
    if r is None:
        prochains = ", ".join(f"« {x['titre']} »" for x in _agenda.a_venir()[:10])
        raise ErreurOutil(f"Je ne trouve pas « {titre} » dans l'agenda."
                          + (f" Rendez-vous à venir : {prochains}." if prochains else " L'agenda est vide."))
    _agenda.supprimer(r["id"])
    return f"Supprimé de l'agenda : {decrire_rendez_vous(r)}."


SCHEMAS = [
    {
        "name": "agenda",
        "description": (
            "Agenda, rappels et minuteurs de l'utilisateur. action=ajouter : note un rendez-vous ou un rappel "
            "(« rappelle-moi le dentiste mardi à 15 h », « mes médicaments tous les jours à 8 h »), ou lance un "
            "minuteur (« mets un minuteur de 10 minutes » : titre « Minuteur », quand « 10 minutes ») ; "
            "action=lister : dit ce qui est prévu ; action=supprimer : retire un rendez-vous. "
            "Pour changer l'heure d'un rendez-vous : supprimer puis ajouter."),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["ajouter", "lister", "supprimer"]},
                "titre": {"type": "string", "description": "Ce qu'il faut faire ou le rendez-vous, court (ex. « Dentiste », "
                                                           "« Prendre les médicaments »)"},
                "quand": {"type": "string", "description": (
                    "Le moment EXACTEMENT comme l'utilisateur l'a dit, sans le transformer ni calculer de date "
                    "(ex. « mardi à 15 h », « demain matin », « dans 20 minutes », « 10 minutes », « tous les jours à 8 h »)")},
                "repetition": {"type": "string", "enum": ["aucune", "jour", "semaine", "mois", "an"],
                               "description": "Si cela se répète"},
                "rappel_avant": {"type": "integer", "description": "Minutes de rappel avant le rendez-vous, si "
                                                                   "l'utilisateur le demande (ex. 60 pour une heure avant)"},
                "periode": {"type": "string", "enum": ["aujourd'hui", "demain", "semaine", "mois", "tout"],
                            "description": "Pour lister"},
            },
            "required": ["action"],
        },
    },
]

FONCTIONS = {"agenda": agenda}
