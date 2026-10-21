"""Outil « email » : préparer un e-mail dans Gmail ou Outlook, que l'utilisateur relit puis envoie lui-même.

Raya n'envoie jamais rien. L'adresse vient du carnet de contacts ou des mots de l'utilisateur : le modèle
ne peut pas en inventer une.
"""
import re
from typing import Callable
from urllib.parse import quote

from raya.outils import navigation
from raya.outils.fichiers import ErreurOutil
from raya.stockage.memoire import ADRESSE_EMAIL, Memoire

MESSAGERIES = {"gmail": "Gmail", "outlook": "Outlook (Hotmail, Outlook.com)"}
PAGES_REDACTION = {
    "gmail": "https://mail.google.com/mail/?view=cm&fs=1&to={a}&su={objet}&body={texte}",
    "outlook": "https://outlook.live.com/mail/0/deeplink/compose?to={a}&subject={objet}&body={texte}",
}
LONGUEUR_MAX_TEXTE = 1800  # au-delà, certaines adresses web deviennent trop longues
SIGNATURE_ASSISTANT = re.compile(
    r"\n+\s*(raya|(votre |ton )?assistant(e)?( raya| vocale?| personnelle?)?|\[[^\]\n]*\])\s*\.?\s*$", re.I)

_memoire: Memoire | None = None
_messagerie: Callable[[], str] = lambda: "gmail"


def configurer(memoire: Memoire, messagerie: Callable[[], str]) -> None:
    global _memoire, _messagerie
    _memoire, _messagerie = memoire, messagerie


def adresses_dites(texte: str) -> list[str]:
    """Adresses e-mail écrites ou dictées : « nicole point martin arobase gmail point com » → nicole.martin@gmail.com."""
    t = f" {texte.lower()} "
    for dit, ecrit in ((" arobase ", "@"), (" arrobase ", "@"), (" at ", "@"), (" tiret bas ", "_"),
                       (" underscore ", "_"), (" tiret ", "-"), (" point ", ".")):
        t = t.replace(dit, ecrit)
    t = re.sub(r"\s*([@.])\s*", r"\1", t)
    return list(dict.fromkeys(m.group(0).rstrip(".") for m in ADRESSE_EMAIL.finditer(t)))


def email(action: str, destinataire: str = "", objet: str = "", message: str = "", nom: str = "", adresse: str = "") -> str:
    if _memoire is None:
        raise ErreurOutil("Le carnet d'adresses n'est pas disponible.")
    action = (action or "").lower()
    if action.startswith("prepar") or action.startswith("écri") or action.startswith("ecri"):
        return _preparer(destinataire, objet, message)
    if "contact" in action:  # ancienne action, désormais dans l'outil carnet
        from raya.outils import carnet
        return carnet.ajouter(nom or destinataire, email=adresse)
    raise ErreurOutil("Action inconnue : utilise « preparer ».")


def adresse_verifiee(adresse: str) -> str | None:
    """L'adresse, seulement si l'utilisateur l'a donnée dans son message ou si elle est dans le carnet."""
    adresse = adresse.lower()
    connues = adresses_dites(navigation.contexte.derniere_demande) + [c["email"] for c in _memoire.contacts() if c["email"]]
    return adresse if adresse in connues else None


def _destinataire(destinataire: str) -> tuple[str, str, str]:
    """Renvoie (nom, adresse, remarque)."""
    if ecrites := adresses_dites(destinataire):
        if not (adresse := adresse_verifiee(ecrites[0])):
            raise ErreurOutil("Cette adresse n'a été ni donnée par l'utilisateur ni trouvée dans le carnet : ne "
                              "l'invente pas. Demande-lui l'adresse e-mail exacte. Rien n'a été préparé.")
        contact = next((c for c in _memoire.contacts() if c["email"] == adresse), None)
        return (contact["nom"] if contact else adresse), adresse, ""
    if re.fullmatch(r"\s*(a |à )?moi([- ]m[eê]me)?\s*", destinataire.lower()):
        destinataire = "moi"  # « envoie-moi… » : le contact « Moi (prénom) » créé à l'accueil
    trouves = _memoire.trouver_contacts(destinataire)
    dites = adresses_dites(navigation.contexte.derniere_demande)
    if len(trouves) == 1 and not trouves[0]["email"] and len(dites) == 1:
        # Contact connu par son seul numéro : l'adresse donnée dans la même phrase le complète
        _memoire.ajouter_contact(trouves[0]["nom"], dites[0])
        return trouves[0]["nom"], dites[0], f" L'adresse de « {trouves[0]['nom']} » a été ajoutée au carnet."
    if len(trouves) == 1 and not trouves[0]["email"]:
        raise ErreurOutil(f"« {trouves[0]['nom']} » est dans le carnet, mais sans adresse e-mail. Demande-la à "
                          "l'utilisateur. Quand il l'a donnée, enregistre-la (outil carnet, action=ajouter) puis "
                          "prépare le message. Rien n'a été préparé.")
    if len(trouves) == 1:
        return trouves[0]["nom"], trouves[0]["email"], ""
    if len(trouves) > 1:
        noms = ", ".join(f"{c['nom']} ({c['email']})" for c in trouves)
        raise ErreurOutil(f"Plusieurs contacts correspondent à « {destinataire} » : {noms}. Demande lequel.")
    # Pas dans le carnet : l'utilisateur a peut-être donné l'adresse dans la même phrase
    if len(dites) == 1 and destinataire.strip():
        _memoire.ajouter_contact(destinataire.strip(), dites[0])
        return destinataire.strip(), dites[0], f" « {destinataire.strip()} » a été ajouté(e) au carnet d'adresses."
    raise ErreurOutil(f"« {destinataire} » n'est pas dans le carnet d'adresses. Demande son adresse e-mail à "
                      "l'utilisateur. Quand il l'a donnée, enregistre-la (outil carnet, action=ajouter) puis prépare le "
                      "message. Rien n'a été préparé.")


def _preparer(destinataire: str, objet: str, message: str) -> str:
    if not (destinataire or "").strip():
        raise ErreurOutil("Indique à qui écrire.")
    if not (message or "").strip():
        raise ErreurOutil("Écris le texte du message (champ message).")
    nom, adresse, remarque = _destinataire(destinataire)
    # Le message part au nom de l'utilisateur : pas de signature « Raya » ou « Votre assistante »
    texte = SIGNATURE_ASSISTANT.sub("", message.strip()).strip()
    if len(texte) > LONGUEUR_MAX_TEXTE:
        raise ErreurOutil(f"Le message est trop long pour être préparé ainsi ({len(texte)} caractères, "
                          f"{LONGUEUR_MAX_TEXTE} au plus) : raccourcis-le.")
    messagerie = _messagerie() if _messagerie() in PAGES_REDACTION else "gmail"
    navigation._ouvrir(PAGES_REDACTION[messagerie].format(a=quote(adresse), objet=quote((objet or "").strip()),
                                                         texte=quote(texte)))
    return (f"Message préparé dans {MESSAGERIES[messagerie].split(' (')[0]}, mais PAS envoyé. Destinataire : {nom} "
            f"<{adresse}>.{remarque} Dis à l'utilisateur que le message est ouvert dans son navigateur, qu'il "
            "doit le relire puis cliquer lui-même sur « Envoyer ». Ne dis jamais que le message est envoyé.")


SCHEMAS = [
    {
        "name": "email",
        "description": (
            "E-mails. action=preparer : rédige un e-mail et l'ouvre dans la messagerie de l'utilisateur (Gmail ou "
            "Outlook), prêt à être relu ; c'est l'utilisateur qui clique sur Envoyer. destinataire = le nom de la "
            "personne tel que l'utilisateur l'a dit (ex. « Nicole »), jamais une adresse inventée. "
            "Pour enregistrer une adresse dans le carnet, utilise l'outil carnet."),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["preparer"]},
                "destinataire": {"type": "string", "description": "Nom de la personne (ou adresse dite par l'utilisateur)"},
                "objet": {"type": "string", "description": "Objet court du message"},
                "message": {"type": "string", "description": "Texte complet du message, avec formule de politesse"},
            },
            "required": ["action"],
        },
    },
]

FONCTIONS = {"email": email}
