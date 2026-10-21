"""Détection des informations sensibles qu'on ne mémorise jamais."""
import re

MOTS_SENSIBLES = re.compile(
    r"mot(s)? de passe|\bmdp\b|password|code (pin|secret|confidentiel|d'accès|d'acces|de la carte)|"
    r"cryptogramme|\bcvv\b|identifiant(s)? (bancaire|de connexion)",
    re.I,
)
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,3})?\b", re.I)
SECU = re.compile(r"\b[12][ .]?\d{2}[ .]?(?:0[1-9]|1[0-2]|[2-9]\d)[ .]?(?:\d{2}|2A|2B)[ .]?\d{3}[ .]?\d{3}(?:[ .]?\d{2})?\b", re.I)
SUITE_CHIFFRES = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(chiffres: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(chiffres)):
        n = int(c)
        if i % 2 == 1:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def raison_sensible(texte: str) -> str | None:
    """Renvoie la nature de l'information sensible trouvée, ou None."""
    if MOTS_SENSIBLES.search(texte):
        return "un mot de passe ou un code secret"
    if IBAN.search(texte.replace("-", " ")):
        return "des coordonnées bancaires (IBAN)"
    for m in SUITE_CHIFFRES.finditer(texte):
        chiffres = re.sub(r"\D", "", m.group())
        if 13 <= len(chiffres) <= 19 and _luhn(chiffres):
            return "un numéro de carte bancaire"
    if SECU.search(texte) or (re.search(r"s[ée]curit[ée] sociale|\bsécu\b|\bsecu\b", texte, re.I) and re.search(r"\d{6,}", texte.replace(" ", ""))):
        return "un numéro de Sécurité sociale"
    return None


def masquer(texte: str) -> str:
    """Remplace les longues suites de chiffres et les IBAN par « [masqué] » (pour les résumés)."""
    texte = IBAN.sub("[masqué]", texte)
    return re.sub(r"\b(?:\d[ .-]?){9,}\d\b", "[masqué]", texte)
