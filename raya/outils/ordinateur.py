"""Outil « ouvrir_fichier » : ouvrir un fichier ou un dossier de l'ordinateur avec son programme habituel.

Les programmes et raccourcis (.exe, .lnk…) ne sont jamais lancés : seuls les documents, images,
musiques, vidéos et dossiers sont ouverts.
"""
import re
from pathlib import Path

from raya.outils import excel, word
from raya.outils.fichiers import (
    DOSSIERS_WINDOWS, ErreurOutil, chercher, cle_dossier, decrire_fichier, dossier_demande, emplacement_lisible, ouvrir,
)
from raya.outils.navigation import contexte

EXTENSIONS_INTERDITES = {
    ".exe", ".msi", ".msix", ".appx", ".bat", ".cmd", ".com", ".scr", ".pif", ".cpl", ".ps1", ".psm1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".jar", ".reg", ".lnk", ".url", ".appref-ms",
}
LECTEURS = {**{ext: word.lire_document for ext in (".docx", ".odt", ".pdf", ".txt", ".md")},
            **{ext: excel.lire_tableau_excel for ext in excel.EXTENSIONS_LECTURE}}
LECTURE = re.compile(r"\b(lis|lisez|lire|relis|lisez-moi|que dit|qu'est-ce que dit|r[ée]sume|r[ée]sumez|contenu|contient)\b", re.I)
OUVERTURE = re.compile(r"\bouvr", re.I)


def ouvrir_fichier(nom: str = "", dossier: str = "") -> str:
    nom, dossier = (nom or "").strip(), (dossier or "").strip()

    # « Ouvre mon bureau », « ouvre mes téléchargements » : le dossier lui-même
    if nom and (cle := cle_dossier(nom)) and (not dossier or cle_dossier(dossier) == cle):
        nom, dossier = "", nom
    if not nom:
        if not dossier:
            raise ErreurOutil("Indique le nom du fichier ou du dossier à ouvrir.")
        chemin = dossier_demande(dossier)
        ouvrir(chemin)
        return f"Le dossier {emplacement_lisible(chemin)} est ouvert dans l'Explorateur de fichiers."

    p = Path(nom.strip('"'))
    chemin = p if p.is_absolute() and p.exists() else chercher(nom, dossier, dossiers_aussi=True)
    if chemin.suffix.lower() in EXTENSIONS_INTERDITES:
        raise ErreurOutil(f"« {chemin.name} » est un programme ou un raccourci : je n'ouvre pas les programmes. "
                          "Dis à l'utilisateur de double-cliquer dessus lui-même s'il le souhaite.")
    # Le modèle confond parfois « lis-moi » et « ouvre » : si l'utilisateur veut le contenu, on le lit
    demande = contexte.derniere_demande
    lire = LECTEURS.get(chemin.suffix.lower()) if LECTURE.search(demande) else None
    if lire and not OUVERTURE.search(demande):
        return lire(str(chemin))
    ouvrir(chemin)
    if chemin.is_dir():
        return f"Le dossier {emplacement_lisible(chemin)} est ouvert dans l'Explorateur de fichiers."
    if lire:
        return "Fichier ouvert à l'écran. " + decrire_fichier(chemin) + "\n\n" + lire(str(chemin))
    return ("Fichier ouvert à l'écran avec son programme habituel. Tu n'as PAS lu son contenu : n'en dis rien. "
            "Si l'utilisateur veut savoir ce qu'il contient, appelle lire_document ou tableau (action=lire). "
            + decrire_fichier(chemin))


NOMS_DOSSIERS = ", ".join(nom for nom, _, _ in DOSSIERS_WINDOWS.values())

# « EXOS BASES.xls — LibreOffice Calc », « Budget [Mode de compatibilité] - Excel », « *notes.txt - Bloc-notes »
# Les navigateurs sont exclus : le titre d'une page web est choisi par le site, pas par l'utilisateur.
TITRE_DOCUMENT = re.compile(
    r"^[*●\s]*(?P<nom>.+?)\s+[-—–]\s+(?P<programme>LibreOffice(?: Calc| Writer| Impress)?|(?:Microsoft )?Excel|"
    r"(?:Microsoft )?Word|(?:Microsoft )?PowerPoint|Bloc-notes|Notepad|WordPad|Adobe Acrobat.*|Acrobat Reader.*)$")
MENTIONS_TITRE = re.compile(r"\s*[\[(](mode de compatibilit[ée]|lecture seule|read-only|compatibility mode)[\])]", re.I)


def fichiers_ouverts() -> list[str]:
    """Documents affichés à l'écran en ce moment, d'après le titre des fenêtres : [« EXOS BASES.xls (LibreOffice Calc) »]."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
    except (AttributeError, OSError):
        return []
    titres: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def rappel(fenetre, _):
        if user32.IsWindowVisible(fenetre) and (longueur := user32.GetWindowTextLengthW(fenetre)):
            tampon = ctypes.create_unicode_buffer(longueur + 1)
            user32.GetWindowTextW(fenetre, tampon, longueur + 1)
            titres.append(tampon.value)
        return True

    user32.EnumWindows(rappel, 0)
    documents = []
    for titre in titres:
        if m := TITRE_DOCUMENT.match(titre.strip()):
            documents.append(f"{MENTIONS_TITRE.sub('', m['nom']).strip()} ({m['programme']})")
    return list(dict.fromkeys(documents))[:10]


SCHEMAS = [
    {
        "name": "ouvrir_fichier",
        "description": (
            "Affiche à l'écran un fichier ou un dossier de l'ordinateur, avec son programme habituel "
            "(ex. « ouvre le fichier factures sur mon bureau » → nom=factures, dossier=Bureau ; "
            "« ouvre mes téléchargements » → dossier=Téléchargements). Il suffit d'une partie du nom. "
            "Ne lit PAS le contenu : si l'utilisateur dit « lis », « lis-moi », « que dit », « résume », "
            "utilise lire_document (ou tableau avec action=lire pour Excel) à la place."),
        "parameters": {
            "type": "object",
            "properties": {
                "nom": {"type": "string", "description": "Nom (ou partie du nom) du fichier ou du dossier, ou chemin complet"},
                "dossier": {"type": "string", "description": f"Où chercher, seulement si l'utilisateur l'a dit : {NOMS_DOSSIERS}. Sinon, laisser vide"},
            },
        },
    },
]

FONCTIONS = {"ouvrir_fichier": ouvrir_fichier}
