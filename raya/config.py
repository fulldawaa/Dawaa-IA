"""Chemins de l'application et réglages utilisateur (config.json)."""
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

NOM_APP = "Raya"

# Dossier des données utilisateur : %APPDATA%\Raya
DOSSIER_DONNEES = Path(os.environ.get("APPDATA", Path.home())) / NOM_APP
DOSSIER_MODELES = DOSSIER_DONNEES / "modeles"
FICHIER_CONFIG = DOSSIER_DONNEES / "config.json"
FICHIER_HISTORIQUE = DOSSIER_DONNEES / "historique.sqlite"

# Dossier où Raya enregistre les fichiers créés : Documents\Raya
DOSSIER_DOCUMENTS = Path.home() / "Documents" / NOM_APP


def dossier_application() -> Path:
    """Racine du programme : le dossier de l'exe une fois packagé, la racine du projet sinon."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def chemin_llama_server() -> Path:
    return dossier_application() / "vendor" / "llama" / "llama-server.exe"


def chemin_ui() -> Path:
    return dossier_application() / "raya" / "ui"


# Taille du texte en pixels : grande par défaut, l'application s'adresse surtout à des personnes âgées
TAILLE_TEXTE_DEFAUT = 20
TAILLE_TEXTE_MIN, TAILLE_TEXTE_MAX = 16, 32
ANCIENNE_TAILLE_TEXTE = 16  # défaut des versions 0.1 et 0.2


@dataclass
class Reglages:
    touche_parler: str = "ctrl_r"  # nom de touche pynput
    voix: str = "fr-FR-DeniseNeural"
    taille_texte: int = TAILLE_TEXTE_DEFAUT
    modele: str = ""  # nom du fichier GGUF choisi au premier lancement
    modele_voix: str = "small"
    demarrer_avec_windows: bool = True  # pour que les rappels de l'agenda sonnent
    son_alarme: str = "Alarm01"  # son d'alarme de Windows, « » = pas de sonnerie
    messagerie: str = "gmail"  # gmail ou outlook : où les e-mails préparés s'ouvrent
    # Accueil du premier lancement
    prenom: str = ""
    email: str = ""
    usages: list = field(default_factory=list)  # ce que l'utilisateur veut faire (voir accueil.USAGES)
    accueil_fait: bool = False
    extras: dict = field(default_factory=dict)

    def enregistrer(self) -> None:
        DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
        FICHIER_CONFIG.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def charger(cls) -> "Reglages":
        try:
            donnees = json.loads(FICHIER_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        connus = {k: v for k, v in donnees.items() if k in cls.__dataclass_fields__}
        reglages = cls(**connus)
        # Une seule fois : l'ancienne taille par défaut passe à la nouvelle (une taille choisie ensuite est gardée)
        if not reglages.extras.get("texte_agrandi"):
            if reglages.taille_texte == ANCIENNE_TAILLE_TEXTE:
                reglages.taille_texte = TAILLE_TEXTE_DEFAUT
            reglages.extras["texte_agrandi"] = True
        return reglages


ANCIEN_NOM_APP = "Dawaa"  # nom de l'application avant la version 0.4.0


def reprendre_ancien_nom(paires: list[tuple[Path, Path]] | None = None) -> list[Path]:
    """Renomme les dossiers d'une installation de Dawaa : modèles, mémoire et documents sont gardés.

    Rien n'est fait si le nouveau dossier existe déjà ; renvoie les dossiers renommés.
    """
    if paires is None:
        paires = [(DOSSIER_DONNEES.with_name(ANCIEN_NOM_APP), DOSSIER_DONNEES),
                  (DOSSIER_DOCUMENTS.with_name(ANCIEN_NOM_APP), DOSSIER_DOCUMENTS)]
    renommes = []
    for ancien, nouveau in paires:
        # Juste après la mise à jour, l'ancien Dawaa peut encore tenir ses fichiers ouverts quelques secondes
        for _ in range(10):
            if not ancien.is_dir() or nouveau.exists():
                break
            try:
                ancien.rename(nouveau)
                renommes.append(nouveau)
            except OSError:
                time.sleep(1)
    return renommes


def preparer_dossiers() -> None:
    for d in (DOSSIER_DONNEES, DOSSIER_MODELES, DOSSIER_DOCUMENTS):
        d.mkdir(parents=True, exist_ok=True)
