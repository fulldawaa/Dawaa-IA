"""Registre des outils que le modèle peut appeler."""
import json
import logging

from dawaa.outils import agenda, email, excel, navigation, ordinateur, souvenirs, web, word
from dawaa.outils.fichiers import ErreurOutil

log = logging.getLogger(__name__)

MODULES = (web, navigation, ordinateur, word, excel, souvenirs, agenda, email)
FONCTIONS = {nom: f for m in MODULES for nom, f in m.FONCTIONS.items()}
SCHEMAS = [{"type": "function", "function": s} for m in MODULES for s in m.SCHEMAS]

# Phrase courte affichée pendant que l'outil travaille
MESSAGES_ATTENTE = {
    "recherche_web": "Je cherche sur internet…",
    "lire_page_web": "Je lis la page…",
    "creer_document_word": "Je prépare le document Word…",
    "lire_document": "Je lis le document…",
    "tableau": "Je travaille sur le tableau…",
    "ouvrir_site": "J'ouvre le site…",
    "ouvrir_fichier": "J'ouvre le fichier…",
    "memoire": "Je note…",
    "agenda": "Je regarde l'agenda…",
    "email": "Je prépare l'e-mail…",
}
MESSAGES_TABLEAU = {"lire": "Je lis le tableau…", "creer": "Je crée le tableau Excel…",
                    "modifier": "Je modifie le tableau…", "graphique": "J'ajoute le graphique…"}


def message_attente(nom: str, arguments: str) -> str:
    """Phrase affichée pendant que l'outil travaille, selon l'outil et l'action demandée."""
    if nom == "memoire" and "lancer_raccourci" in arguments:
        return "Je lance le raccourci…"
    if nom == "tableau" and (action := next((a for a in MESSAGES_TABLEAU if f'"{a}"' in arguments), None)):
        return MESSAGES_TABLEAU[action]
    return MESSAGES_ATTENTE.get("tableau" if nom in excel.ANCIENS_OUTILS else nom, "Je travaille…")


# Actions qu'un raccourci peut rejouer : elles affichent ou lisent, sans rien créer ni modifier
REJOUABLES = {"recherche_web", "lire_page_web", "ouvrir_site", "ouvrir_fichier", "lire_document"}
MAX_ACTIONS_JOURNAL = 10
# Actions rejouables réussies depuis le début de la conversation (ou depuis le dernier raccourci enregistré)
journal: list[dict] = []


def executer(nom: str, arguments: str | dict, rejeu: bool = False) -> str:
    """Exécute un outil et renvoie toujours un texte (jamais d'exception) pour le modèle."""
    resultat, args, nom = _executer(nom, arguments)
    rejouable = nom in REJOUABLES or nom == "tableau" and args.get("action") == "lire"
    if not rejeu and rejouable and not resultat.startswith(("Erreur", "[proposition de site")):
        action = {"outil": nom, "arguments": args, "demande": navigation.contexte.derniere_demande}
        if not journal or {**journal[-1], "demande": ""} != {**action, "demande": ""}:
            journal.append(action)
            del journal[:-MAX_ACTIONS_JOURNAL]
    return resultat


def _executer(nom: str, arguments: str | dict) -> tuple[str, dict, str]:
    """Renvoie (résultat, arguments, nom de l'outil réellement appelé)."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except ValueError:
        return "Erreur : arguments illisibles. Réessaie avec un JSON valide.", {}, nom
    if nom in excel.ANCIENS_OUTILS:  # raccourci enregistré avant la fusion des outils Excel
        nom, args = "tableau", {**args, "action": excel.ANCIENS_OUTILS[nom]}
    fonction = FONCTIONS.get(nom)
    if fonction is None:
        return f"Erreur : l'outil « {nom} » n'existe pas.", args, nom
    try:
        return fonction(**args), args, nom
    except ErreurOutil as e:
        return f"Erreur : {e}", args, nom
    except TypeError as e:
        return f"Erreur : paramètres incorrects ({e}).", args, nom
    except Exception as e:
        log.exception("Outil %s en échec", nom)
        return f"Erreur inattendue : {e}", args, nom
