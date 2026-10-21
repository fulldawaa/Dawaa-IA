"""Outil « carnet » : le carnet d'adresses (e-mails et numéros de téléphone de l'entourage).

On n'enregistre qu'une adresse ou un numéro que l'utilisateur a dit ou écrit lui-même, et on ne redonne
que ce qui est dans le carnet : le modèle ne peut ni inventer ni deviner un numéro.
"""
import re

from raya.outils import email as outil_email
from raya.outils import navigation
from raya.outils.fichiers import ErreurOutil
from raya.stockage.memoire import NUMERO_ECRIT, Memoire, numero_telephone

_memoire: Memoire | None = None


def configurer(memoire: Memoire) -> None:
    global _memoire
    _memoire = memoire


def _chiffres(texte: str) -> str:
    return re.sub(r"\D", "", texte)


def numero_dit(numero: str) -> str | None:
    """Le numéro au format lisible, seulement si l'utilisateur l'a donné dans son message."""
    dits = [n for m in NUMERO_ECRIT.finditer(navigation.contexte.derniere_demande) if (n := numero_telephone(m.group()))]
    if not (numero or "").strip():
        return dits[0] if len(dits) == 1 else None
    # On compare les 9 derniers chiffres : « +33 6 12… » et « 06 12… » sont le même numéro
    cle = _chiffres(numero_telephone(numero) or "")[-9:]
    return next((n for n in dits if cle and _chiffres(n)[-9:] == cle), None)


def _decrire(contact: dict) -> str:
    coordonnees = [f"téléphone {contact['telephone']}" if contact["telephone"] else "pas de numéro de téléphone",
                   f"e-mail {contact['email']}" if contact["email"] else "pas d'adresse e-mail"]
    return f"{contact['nom']} : " + ", ".join(coordonnees)


def carnet(action: str, nom: str = "", telephone: str = "", email: str = "") -> str:
    if _memoire is None:
        raise ErreurOutil("Le carnet d'adresses n'est pas disponible.")
    action = (action or "").lower()
    if action.startswith("ajout") or action.startswith("enregistr"):
        return ajouter(nom, telephone, email)
    if action.startswith("cherch") or action.startswith("trouv") or action.startswith("lire"):
        return chercher(nom)
    raise ErreurOutil("Action inconnue : utilise « ajouter » ou « chercher ».")


def ajouter(nom: str, telephone: str = "", email: str = "") -> str:
    if not (nom or "").strip():
        raise ErreurOutil("Indique le nom de la personne.")
    demande = navigation.contexte.derniere_demande
    numero = adresse = ""
    if telephone or numero_telephone(demande):
        if not (numero := numero_dit(telephone)):
            raise ErreurOutil("Je n'enregistre que le numéro que l'utilisateur a donné lui-même dans son message. "
                              "Demande-lui de le dire ou de l'écrire, chiffre par chiffre.")
    if email or outil_email.adresses_dites(demande):
        ecrites = outil_email.adresses_dites(email or "") or outil_email.adresses_dites(demande)
        if not ecrites or not (adresse := outil_email.adresse_verifiee(ecrites[0])):
            raise ErreurOutil("Je n'enregistre que l'adresse que l'utilisateur a donnée lui-même dans son message. "
                              "Demande-lui de la dire ou de l'écrire.")
    if not numero and not adresse:
        raise ErreurOutil("Demande à l'utilisateur le numéro de téléphone ou l'adresse e-mail à enregistrer.")
    try:
        _, remplace = _memoire.ajouter_contact(nom, adresse, numero)
    except ValueError as e:
        raise ErreurOutil(str(e)) from None
    enregistre = " et ".join(x for x in (numero, adresse) if x)
    a_verifier = "le numéro" if numero else "l'adresse"
    return (f"{'Contact mis à jour' if remplace else 'Contact enregistré'} : {nom.strip()} — {enregistre}. "
            f"Répète {a_verifier} à l'utilisateur pour qu'il vérifie.")


def chercher(nom: str) -> str:
    if not (nom or "").strip():
        raise ErreurOutil("Indique le nom de la personne à chercher.")
    trouves = _memoire.trouver_contacts(nom)
    if not trouves:
        return (f"« {nom} » n'est pas dans le carnet d'adresses. Ne devine aucun numéro ni aucune adresse : "
                "dis-le à l'utilisateur et propose-lui de l'ajouter (il te donne le numéro ou l'adresse).")
    if len(trouves) > 1:
        return "Plusieurs contacts correspondent :\n" + "\n".join(f"- {_decrire(c)}" for c in trouves)
    return _decrire(trouves[0]) + ". Donne ces informations telles quelles."


SCHEMAS = [
    {
        "name": "carnet",
        "description": (
            "Carnet d'adresses de l'utilisateur (numéros de téléphone et e-mails de ses proches). "
            "action=ajouter : enregistre le numéro et/ou l'adresse que l'utilisateur vient de donner. "
            "action=chercher : retrouve le numéro ou l'adresse d'une personne (« quel est le numéro de Nicole ? »)."),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["ajouter", "chercher"]},
                "nom": {"type": "string", "description": "Nom de la personne, tel que l'utilisateur l'a dit"},
                "telephone": {"type": "string", "description": "Pour ajouter : numéro donné par l'utilisateur"},
                "email": {"type": "string", "description": "Pour ajouter : adresse donnée par l'utilisateur"},
            },
            "required": ["action", "nom"],
        },
    },
]

FONCTIONS = {"carnet": carnet}
