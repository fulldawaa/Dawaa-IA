"""Outil « memoire » : retenir ou oublier une information sur l'utilisateur, enregistrer et lancer des raccourcis.

Un raccourci est une suite d'actions déjà faites (ouvrir un site, lire un fichier…), rejouées telles
quelles à la demande : le modèle n'a pas à les reconstituer.
"""
import re
from pathlib import Path

from dawaa.outils import navigation
from dawaa.outils.fichiers import ErreurOutil
from dawaa.stockage.memoire import Memoire
from dawaa.stockage.sensible import raison_sensible

MARQUE_SOUVENIR = "[souvenir n°{id}]"
MAX_CARACTERES_REJEU = 6000

VERBES = r"(?:s'appelle|est|sont|habite|vit|a|ont|aime|adore|préfère|déteste|travaille|joue|fait|utilise|souhaite|veut)"
PRONOM = r"(?:il|elle|ils|elles|son|sa|ses|leur|leurs)"
# Sujet qui désigne une personne ou un animal (et non « Son prénom », « Son adresse »…)
PERSONNE = (r"^(?:\S+\s+)?(?:\S+\s+)?(?:fille|fils|femme|mari|épouse|époux|compagne?|mère|père|maman|papa|frère|sœur|"
            r"soeur|enfant|petite?-(?:fille|fils)|ami|amie|voisine?|médecin|docteur|chien|chat|neveu|nièce)\b")


def decouper(texte: str) -> list[str]:
    """Une information par souvenir, pour pouvoir en oublier une sans perdre les autres.

    « Sa fille s'appelle Léa et a 12 ans » → [« Sa fille s'appelle Léa », « Sa fille a 12 ans »]
    « Son prénom est Michel et il habite à Lyon » → [« Son prénom est Michel », « Il habite à Lyon »]
    """
    texte = texte.strip().rstrip(".")
    sujet = re.match(rf"^(.+?)\s{VERBES}\b", texte)
    parties = re.split(rf",?\s+et\s+(?=(?:{PRONOM}|{VERBES})\b)", texte)
    resultat = []
    for i, partie in enumerate(parties):
        partie = partie.strip()
        if i > 0 and re.match(rf"{VERBES}\b", partie):
            if not sujet:
                return [texte]  # sujet introuvable : on garde la phrase entière
            partie = f"{sujet.group(1)} {partie}"
        elif i > 0 and sujet and re.match(PERSONNE, sujet.group(1), re.I) and re.match(r"(il|elle) ", partie, re.I):
            # « La fille de Michel s'appelle Léa et elle a 12 ans » → « La fille de Michel a 12 ans »
            partie = f"{sujet.group(1)} {partie.split(' ', 1)[1]}"
        resultat.append(partie[0].upper() + partie[1:])
    return resultat
_memoire: Memoire | None = None


def configurer(memoire: Memoire) -> None:
    global _memoire
    _memoire = memoire


def memoire(action: str, texte: str) -> str:
    if _memoire is None:
        raise ErreurOutil("La mémoire n'est pas disponible.")
    action = (action or "").lower()
    texte = (texte or "").strip()
    if not texte:
        raise ErreurOutil("Il faut indiquer ce qu'il faut retenir ou oublier.")
    if action.startswith("retenir"):
        if raison := raison_sensible(texte):
            return (f"Refusé : cela contient {raison}. Par sécurité, je ne retiens jamais ce genre d'information. "
                    "Explique-le gentiment à l'utilisateur et conseille-lui de le garder en lieu sûr.")
        lignes = []
        for partie in decouper(texte):
            id_, remplace = _memoire.retenir(partie)
            debut = "Souvenir mis à jour" if remplace else "Retenu"
            lignes.append(f"{debut} {MARQUE_SOUVENIR.format(id=id_)} : {partie}")
        return "\n".join(lignes)
    if action.startswith("enregistrer"):
        return enregistrer_raccourci(texte)
    if action.startswith("lancer"):
        return lancer_raccourci(texte)
    if action.startswith("oubli"):
        if raccourci := _memoire.trouver_raccourci(texte, exact=True):
            _memoire.supprimer_raccourci(raccourci["id"])
            return f"Raccourci « {raccourci['nom']} » supprimé."
        oublie = _memoire.oublier(texte)
        if oublie is None:
            if raccourci := _memoire.trouver_raccourci(texte):
                _memoire.supprimer_raccourci(raccourci["id"])
                return f"Raccourci « {raccourci['nom']} » supprimé."
            return "Je n'avais rien retenu qui corresponde. Dis-le simplement à l'utilisateur."
        return (f"Oublié : {oublie} Si ce souvenir contenait aussi d'autres informations que l'utilisateur "
                "n'a pas demandé d'oublier, retiens-les à nouveau (action=retenir).")
    raise ErreurOutil("Action inconnue : utilise « retenir », « oublier », « enregistrer_raccourci » ou « lancer_raccourci ».")


# ---------- raccourcis ----------

def decrire_action(action: dict) -> str:
    """Phrase simple pour l'utilisateur : « Ouvrir YouTube et chercher « météo » »."""
    a, outil = action["arguments"], action["outil"]
    if outil == "ouvrir_site":
        return f"Ouvrir {a.get('site') or 'Google'}" + (f" et chercher « {a['recherche']} »" if a.get("recherche") else "")
    if outil == "ouvrir_fichier":
        from dawaa.outils.ordinateur import LECTURE, OUVERTURE  # import tardif : ordinateur importe navigation

        verbe = "Lire" if LECTURE.search(action["demande"]) and not OUVERTURE.search(action["demande"]) else "Ouvrir"
        return f"{verbe} {Path(a.get('nom') or '').name or a.get('dossier', '')}".strip()
    if outil in ("lire_document", "lire_tableau_excel", "tableau"):
        return f"Lire {Path(a.get('chemin', '')).name}"
    if outil == "recherche_web":
        return f"Chercher sur internet « {a.get('requete', '')} »"
    if outil == "lire_page_web":
        return f"Lire la page {navigation.domaine(a.get('url', ''))}"
    return outil


def enregistrer_raccourci(nom: str) -> str:
    from dawaa import outils  # import tardif : outils importe ce module

    if not outils.journal:
        raise ErreurOutil("Aucune action à enregistrer dans cette conversation. Seules comptent : ouvrir un site ou "
                          "un fichier, lire un document, chercher sur internet. Dis à l'utilisateur de faire d'abord "
                          "les actions une par une, puis de redemander d'enregistrer le raccourci.")
    actions = list(outils.journal)
    id_, remplace = _memoire.enregistrer_raccourci(nom, actions)
    outils.journal.clear()
    liste = "\n".join(f"{i}. {decrire_action(a)}" for i, a in enumerate(actions, 1))
    return (f"{'Raccourci remplacé' if remplace else 'Raccourci enregistré'} [raccourci n°{id_}] « {nom} », "
            f"avec ces actions :\n{liste}\n"
            f"Dis à l'utilisateur ce que contient le raccourci, qu'il pourra dire « {nom} » pour tout refaire, "
            "et qu'il peut le supprimer dans la page Ma mémoire.")


def lancer_raccourci(nom: str) -> str:
    from dawaa import outils  # import tardif : outils importe ce module

    raccourci = _memoire.trouver_raccourci(nom)
    if raccourci is None:
        noms = ", ".join(f"« {r['nom']} »" for r in _memoire.raccourcis())
        raise ErreurOutil(f"Je n'ai pas de raccourci « {nom} ». "
                          + (f"Raccourcis enregistrés : {noms}." if noms else "Aucun raccourci n'est enregistré."))
    actions = raccourci["actions"]
    taille_max = MAX_CARACTERES_REJEU // len(actions)
    resultats = []
    demande_actuelle = navigation.contexte.derniere_demande
    try:
        for i, action in enumerate(actions, 1):
            # On rejoue dans les mêmes conditions qu'à l'enregistrement (« lis-moi… », adresse donnée par l'utilisateur)
            navigation.contexte.derniere_demande = f"{action['demande']} {action['arguments'].get('site', '')}"
            resultat = outils.executer(action["outil"], action["arguments"], rejeu=True)
            if len(resultat) > taille_max:
                resultat = resultat[:taille_max] + " […]"
            resultats.append(f"{i}. {decrire_action(action)} → {resultat}")
    finally:
        navigation.contexte.derniere_demande = demande_actuelle
    return (f"Raccourci « {raccourci['nom']} » rejoué ({len(actions)} action(s)) :\n\n" + "\n\n".join(resultats)
            + "\n\nRésume à l'utilisateur ce qui a été fait, et ce que disent les documents ou pages lus s'il y en a.")


SCHEMAS = [
    {
        "name": "memoire",
        "description": (
            "Mémoire à long terme. action=retenir : enregistre une information DURABLE sur l'utilisateur "
            "(prénom, famille, ville, habitudes, préférences de réponse, nom de son médecin, adresse à mettre "
            "dans les lettres…), écrite en une phrase courte à la 3e personne, ex. « Sa fille s'appelle Léa ». "
            "UNE seule information par appel : appelle plusieurs fois s'il y en a plusieurs. "
            "Pas pour les demandes ponctuelles. action=oublier : efface ce que l'utilisateur demande d'oublier "
            "(une information ou un raccourci). "
            "action=enregistrer_raccourci : quand l'utilisateur veut garder les actions qu'il vient de faire pour les "
            "refaire plus tard (« retiens ça sous le nom ma routine du matin », « enregistre ça comme raccourci ») ; "
            "texte = le nom du raccourci. action=lancer_raccourci : quand l'utilisateur demande un raccourci "
            "enregistré (« fais ma routine du matin ») ; texte = son nom."),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["retenir", "oublier", "enregistrer_raccourci", "lancer_raccourci"]},
                "texte": {"type": "string", "description": "L'information à retenir, ce qu'il faut oublier, ou le nom du raccourci"},
            },
            "required": ["action", "texte"],
        },
    },
]

FONCTIONS = {"memoire": memoire}
