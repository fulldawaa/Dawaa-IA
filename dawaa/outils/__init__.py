"""Registre des outils que le modèle peut appeler."""
import json
import logging

from dawaa.outils import excel, navigation, ordinateur, souvenirs, web, word
from dawaa.outils.fichiers import ErreurOutil

log = logging.getLogger(__name__)

MODULES = (web, navigation, ordinateur, word, excel, souvenirs)
FONCTIONS = {nom: f for m in MODULES for nom, f in m.FONCTIONS.items()}
SCHEMAS = [{"type": "function", "function": s} for m in MODULES for s in m.SCHEMAS]

# Phrase courte affichée pendant que l'outil travaille
MESSAGES_ATTENTE = {
    "recherche_web": "Je cherche sur internet…",
    "lire_page_web": "Je lis la page…",
    "creer_document_word": "Je prépare le document Word…",
    "lire_document": "Je lis le document…",
    "creer_tableau_excel": "Je crée le tableau Excel…",
    "lire_tableau_excel": "Je lis le tableau…",
    "modifier_tableau_excel": "Je modifie le tableau…",
    "ajouter_graphique_excel": "J'ajoute le graphique…",
    "ouvrir_site": "J'ouvre le site…",
    "ouvrir_fichier": "J'ouvre le fichier…",
    "memoire": "Je note…",
}


# Actions qu'un raccourci peut rejouer : elles affichent ou lisent, sans rien créer ni modifier
REJOUABLES = {"recherche_web", "lire_page_web", "ouvrir_site", "ouvrir_fichier", "lire_document", "lire_tableau_excel"}
MAX_ACTIONS_JOURNAL = 10
# Actions rejouables réussies depuis le début de la conversation (ou depuis le dernier raccourci enregistré)
journal: list[dict] = []


def executer(nom: str, arguments: str | dict, rejeu: bool = False) -> str:
    """Exécute un outil et renvoie toujours un texte (jamais d'exception) pour le modèle."""
    resultat, args = _executer(nom, arguments)
    if not rejeu and nom in REJOUABLES and not resultat.startswith(("Erreur", "[proposition de site")):
        action = {"outil": nom, "arguments": args, "demande": navigation.contexte.derniere_demande}
        if not journal or {**journal[-1], "demande": ""} != {**action, "demande": ""}:
            journal.append(action)
            del journal[:-MAX_ACTIONS_JOURNAL]
    return resultat


def _executer(nom: str, arguments: str | dict) -> tuple[str, dict]:
    fonction = FONCTIONS.get(nom)
    if fonction is None:
        return f"Erreur : l'outil « {nom} » n'existe pas.", {}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
    except ValueError:
        return "Erreur : arguments illisibles. Réessaie avec un JSON valide.", {}
    try:
        return fonction(**args), args
    except ErreurOutil as e:
        return f"Erreur : {e}", args
    except TypeError as e:
        return f"Erreur : paramètres incorrects ({e}).", args
    except Exception as e:
        log.exception("Outil %s en échec", nom)
        return f"Erreur inattendue : {e}", args
