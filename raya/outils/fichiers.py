"""Aides communes : où ranger les fichiers, ne jamais écraser, retrouver un fichier, ouvrir le résultat."""
import os
import re
from pathlib import Path

from raya import config
from raya.stockage.memoire import normaliser

# Désactivable dans les tests
OUVRIR_AUTOMATIQUEMENT = True


class ErreurOutil(Exception):
    """Erreur expliquée simplement, renvoyée telle quelle au modèle."""


def nettoyer_nom(nom: str) -> str:
    nom = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", nom).replace("_", " ").strip(" .")
    return nom[:80] or "document"


def chemin_libre(chemin: Path) -> Path:
    """Renvoie un chemin qui n'existe pas encore : « nom.ext », sinon « nom (2).ext »…"""
    if not chemin.exists():
        return chemin
    n = 2
    while True:
        candidat = chemin.with_name(f"{chemin.stem} ({n}){chemin.suffix}")
        if not candidat.exists():
            return candidat
        n += 1


def nouveau_fichier(nom: str, extension: str) -> Path:
    config.DOSSIER_DOCUMENTS.mkdir(parents=True, exist_ok=True)
    nom = nettoyer_nom(Path(nom).stem if nom.lower().endswith(extension) else nom)
    return chemin_libre(config.DOSSIER_DOCUMENTS / f"{nom}{extension}")


def copie_modifiee(source: Path) -> Path:
    """Chemin de la copie modifiée d'un fichier : l'original n'est jamais écrasé."""
    stem = re.sub(r" \(modifié( \d+)?\)$", "", source.stem)
    dossier = source.parent if os.access(source.parent, os.W_OK) else config.DOSSIER_DOCUMENTS
    candidat = dossier / f"{stem} (modifié){source.suffix}"
    n = 2
    while candidat.exists():
        candidat = dossier / f"{stem} (modifié {n}){source.suffix}"
        n += 1
    return candidat


TYPES_LISIBLES = {
    ".docx": "un document Word (outil lire_document)",
    ".odt": "un document LibreOffice (outil lire_document)",
    ".pdf": "un PDF (outil lire_document)",
    ".txt": "un fichier texte (outil lire_document)",
    ".md": "un fichier texte (outil lire_document)",
    ".xlsx": "un tableau Excel (outil tableau, action=lire)",
    ".xlsm": "un tableau Excel (outil tableau, action=lire)",
    ".xls": "un tableau Excel (outil tableau, action=lire)",
    ".ods": "un tableau LibreOffice Calc (outil tableau, action=lire)",
    ".csv": "un tableau CSV (outil tableau, action=lire)",
}


def _verifier_type(fichier: Path, extensions: tuple[str, ...]) -> Path:
    if fichier.suffix.lower() in extensions:
        return fichier
    if genre := TYPES_LISIBLES.get(fichier.suffix.lower()):
        raise ErreurOutil(f"Le fichier {fichier.name} est {genre}. Chemin pour les outils : {fichier}")
    raise ErreurOutil(f"Je ne sais pas lire ce type de fichier ({fichier.name}), "
                      "mais je peux l'ouvrir avec son programme habituel (outil ouvrir_fichier).")


def fichier_existant(chemin: str, extensions: tuple[str, ...], dossier: str = "") -> Path:
    """Retrouve un fichier : chemin complet, nom rangé dans Documents\\Raya, ou nom cherché dans les dossiers personnels."""
    p = Path(chemin.strip().strip('"'))
    if not dossier:
        candidats = [p] if p.is_absolute() else [config.DOSSIER_DOCUMENTS / p, Path.cwd() / p]
        for c in list(candidats):
            if not c.suffix:
                candidats += [c.with_suffix(ext) for ext in extensions]
        for c in candidats:
            if c.is_file():
                return _verifier_type(c, extensions)
        if p.is_absolute():
            raise ErreurOutil(f"Je ne trouve pas le fichier « {chemin} ».")
    return _verifier_type(chercher(chemin, dossier, extensions), extensions)


# ---------- recherche dans les dossiers personnels (Bureau, Documents…) ----------

# Nom affiché, nom anglais et identifiant Windows : le Bureau peut avoir été déplacé (dans OneDrive par exemple)
DOSSIERS_WINDOWS = {
    "bureau": ("Bureau", "Desktop", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"),
    "documents": ("Documents", "Documents", "FDD39AD0-238F-46AF-ADB4-6C85480369C7"),
    "telechargements": ("Téléchargements", "Downloads", "374DE290-123F-4565-9164-39C4925E467B"),
    "images": ("Images", "Pictures", "33E28130-4E1E-4676-835A-98395C3BC3BB"),
    "videos": ("Vidéos", "Videos", "18989B1D-99B5-455B-841C-AB7C74E4DDFC"),
    "musique": ("Musique", "Music", "4BD8D571-6D19-48D3-BE97-422220080E43"),
}
SYNONYMES_DOSSIERS = {
    "bureau": "bureau", "desktop": "bureau",
    "documents": "documents", "document": "documents",
    "telechargements": "telechargements", "telechargement": "telechargements", "downloads": "telechargements",
    "images": "images", "image": "images", "photos": "images", "photo": "images",
    "videos": "videos", "video": "videos",
    "musique": "musique", "musiques": "musique", "music": "musique",
}
MOTS_INUTILES = re.compile(r"\b(sur|dans|mon|ma|mes|le|la|les|l|dossier|des|du|de|d)\b")
PROFONDEUR_MAX = 3
MAX_ELEMENTS = 20_000
CACHE_OU_SYSTEME = 0x2 | 0x4
NOMS_IGNORES = {"desktop.ini", "thumbs.db"}


def _dossier_windows(identifiant: str, anglais: str) -> Path:
    try:
        import ctypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16),
                        ("d4", ctypes.c_ubyte * 8)]

        guid = GUID.from_buffer_copy(uuid.UUID(identifiant).bytes_le)
        resultat = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(resultat)) == 0:
            chemin = Path(resultat.value)
            ctypes.windll.ole32.CoTaskMemFree(resultat)
            return chemin
    except (AttributeError, OSError, ValueError):
        pass
    return Path.home() / anglais


def dossiers_personnels() -> dict[str, Path]:
    """Dossiers où chercher, dans l'ordre : Bureau, Documents, Téléchargements, Images, Vidéos, Musique."""
    return {cle: _dossier_windows(guid, anglais) for cle, (_, anglais, guid) in DOSSIERS_WINDOWS.items()}


def cle_dossier(texte: str) -> str | None:
    """« mon Bureau » → « bureau », « les photos » → « images » ; None si ce n'est pas un dossier personnel."""
    return SYNONYMES_DOSSIERS.get(" ".join(MOTS_INUTILES.sub(" ", normaliser(texte)).split()))


def dossier_demande(dossier: str) -> Path:
    """Dossier donné par l'utilisateur : chemin complet, « Bureau », ou « Documents > Factures »."""
    if Path(dossier).is_absolute() and Path(dossier).is_dir():
        return Path(dossier)
    premier, *suite = [p.strip() for p in re.split(r"[>/\\]", dossier) if p.strip()] or [""]
    cle = cle_dossier(premier)
    if cle is None:
        noms = ", ".join(nom for nom, _, _ in DOSSIERS_WINDOWS.values())
        raise ErreurOutil(f"Je ne connais pas le dossier « {dossier} ». Dossiers possibles : {noms}.")
    chemin = dossiers_personnels()[cle].joinpath(*suite)
    if not chemin.is_dir():
        raise ErreurOutil(f"Le dossier « {dossier} » n'existe pas.")
    return chemin


def _parcourir(racine: Path):
    """Fichiers et dossiers visibles sous `racine`, sur quelques niveaux, sans suivre les raccourcis de dossiers."""
    a_voir, vus = [(racine, 1)], 0
    while a_voir:
        dossier, profondeur = a_voir.pop(0)
        try:
            entrees = list(os.scandir(dossier))
        except OSError:
            continue
        for e in entrees:
            vus += 1
            if vus > MAX_ELEMENTS:
                return
            if e.name.startswith((".", "~$")) or e.name.lower() in NOMS_IGNORES:
                continue
            try:
                if e.is_symlink() or e.is_junction() or getattr(e.stat(), "st_file_attributes", 0) & CACHE_OU_SYSTEME:
                    continue
                est_dossier = e.is_dir()
            except OSError:
                continue
            yield Path(e.path), est_dossier
            if est_dossier and profondeur < PROFONDEUR_MAX:
                a_voir.append((Path(e.path), profondeur + 1))


MOTS_VIDES = {"le", "la", "les", "l", "de", "du", "des", "d", "un", "une", "mon", "ma", "mes", "a", "au", "aux",
              "et", "en", "pour", "fichier", "document"}


def _mots(texte: str) -> list[str]:
    """Mots utiles sans « s » final : « le courrier de la mairie » → [courrier, mairie], « factures » → [facture]."""
    mots = normaliser(texte).split()
    utiles = [m for m in mots if m not in MOTS_VIDES] or mots
    return [m.rstrip("s") or m for m in utiles]


def _score(recherche: list[str], extension: str, chemin: Path, est_dossier: bool,
           extensions: tuple[str, ...] | None) -> int:
    nom = _mots(chemin.name if est_dossier else chemin.stem)
    if nom == recherche:
        score = 100
    elif " ".join(recherche) in " ".join(nom):
        score = 60
    elif set(recherche) <= set(nom):
        score = 40
    else:
        return 0
    suffixe = "" if est_dossier else chemin.suffix.lower()
    if extension:
        score += 10 if suffixe == extension else -5
    if extensions and suffixe in extensions:
        score += 20
    return score


def _dossier_cite(dossier: str) -> bool:
    """Vrai si l'utilisateur a lui-même parlé de ce dossier : le modèle en devine parfois un."""
    from raya.outils.navigation import contexte  # import tardif : navigation importe ce module

    demande = normaliser(contexte.derniere_demande)
    cle = cle_dossier(re.split(r"[>/\\]", dossier)[0])
    if not demande or cle is None or Path(dossier).is_absolute():
        return True
    return any(c == cle and re.search(rf"\b{s}\b", demande) for s, c in SYNONYMES_DOSSIERS.items())


def chercher(nom: str, dossier: str = "", extensions: tuple[str, ...] | None = None,
             dossiers_aussi: bool = False) -> Path:
    """Cherche un fichier (ou un dossier) par son nom dans les dossiers personnels de l'utilisateur.

    Lève ErreurOutil avec les possibilités si le nom est ambigu ou introuvable.
    """
    # Nom dicté à la voix : « facture point pdf » → « facture.pdf »
    nom = re.sub(r"\s+point\s+(\w{2,4})\s*$", r".\1", nom.strip().strip('"'), flags=re.I)
    suffixe = Path(nom).suffix.lower()
    extension = suffixe if re.fullmatch(r"\.[a-z0-9]{2,4}", suffixe) else ""
    recherche = _mots(Path(nom).stem if extension else nom)
    if not recherche:
        raise ErreurOutil("Indique le nom du fichier.")
    if dossier and not _dossier_cite(dossier):
        dossier = ""
    racines = [dossier_demande(dossier)] if dossier else list(dossiers_personnels().values())

    def trouver(racines: list[Path]) -> dict[Path, int]:
        trouves: dict[Path, int] = {}
        for racine in racines:
            for chemin, est_dossier in _parcourir(racine):
                if est_dossier and not dossiers_aussi:
                    continue
                if (score := _score(recherche, extension, chemin, est_dossier, extensions)) > 0:
                    trouves.setdefault(chemin, score)
        return trouves

    trouves = trouver(racines)
    if not trouves and dossier:  # le modèle devine parfois le dossier : on cherche aussi ailleurs
        trouves = trouver(list(dossiers_personnels().values()))

    if not trouves:
        lieu = emplacement_lisible(racines[0]) if dossier else "le Bureau, les Documents, les Téléchargements, les Images, les Vidéos ni la Musique"
        message = f"Je ne trouve pas « {nom} » dans {lieu}."
        if dossier:
            presents = sorted((p for p in racines[0].iterdir() if not p.name.startswith((".", "~$"))
                               and p.name.lower() not in NOMS_IGNORES), key=lambda p: p.stat().st_mtime, reverse=True)
            if presents:
                message += " Ce dossier contient : " + ", ".join(p.name for p in presents[:15])
                message += f" (et {len(presents) - 15} autres)." if len(presents) > 15 else "."
        raise ErreurOutil(message + " Demande à l'utilisateur de vérifier le nom ou l'endroit.")

    meilleur = max(trouves.values())
    premiers = [p for p, s in trouves.items() if s == meilleur]
    if len(premiers) == 1:
        return premiers[0]
    liste = "\n".join(f"- {emplacement_lisible(p)} (chemin pour les outils : {p})" for p in premiers[:6])
    plus = f"\n(et {len(premiers) - 6} autres : demande un nom plus précis)" if len(premiers) > 6 else ""
    raise ErreurOutil(f"Plusieurs fichiers correspondent à « {nom} » :\n{liste}{plus}\n"
                      "Demande à l'utilisateur lequel il veut (sans lui montrer les chemins), "
                      "puis réessaie avec le chemin exact.")


def ouvrir(chemin: Path) -> None:
    if OUVRIR_AUTOMATIQUEMENT:
        try:
            os.startfile(chemin)  # type: ignore[attr-defined]
        except OSError:
            pass


def emplacement_lisible(chemin: Path) -> str:
    """« Documents > Raya > lettre.docx » ou « Bureau > facture.pdf » plutôt qu'un chemin technique."""
    for cle, racine in dossiers_personnels().items():
        if chemin == racine or racine in chemin.parents:
            return " > ".join([DOSSIERS_WINDOWS[cle][0], *chemin.relative_to(racine).parts])
    try:
        relatif = chemin.relative_to(Path.home())
        return " > ".join(relatif.parts)
    except ValueError:
        return str(chemin)


MARQUE_CHEMIN = "Chemin technique (pour les outils, ne pas montrer) : "


def decrire_fichier(chemin: Path) -> str:
    """Phrase renvoyée au modèle : l'emplacement à annoncer, puis le chemin exact pour les outils."""
    return f"Emplacement à annoncer à l'utilisateur : {emplacement_lisible(chemin)}. {MARQUE_CHEMIN}{chemin}"
