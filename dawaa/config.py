"""Chemins de l'application et réglages utilisateur (config.json)."""
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

NOM_APP = "Dawaa"

# Dossier des données utilisateur : %APPDATA%\Dawaa
DOSSIER_DONNEES = Path(os.environ.get("APPDATA", Path.home())) / NOM_APP
DOSSIER_MODELES = DOSSIER_DONNEES / "modeles"
FICHIER_CONFIG = DOSSIER_DONNEES / "config.json"
FICHIER_HISTORIQUE = DOSSIER_DONNEES / "historique.sqlite"

# Dossier où Dawaa enregistre les fichiers créés : Documents\Dawaa
DOSSIER_DOCUMENTS = Path.home() / "Documents" / NOM_APP


def dossier_application() -> Path:
    """Racine du programme : le dossier de l'exe une fois packagé, la racine du projet sinon."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def chemin_llama_server() -> Path:
    return dossier_application() / "vendor" / "llama" / "llama-server.exe"


def chemin_ui() -> Path:
    return dossier_application() / "dawaa" / "ui"


@dataclass
class Reglages:
    touche_parler: str = "ctrl_r"  # nom de touche pynput
    voix: str = "fr-FR-DeniseNeural"
    taille_texte: int = 16
    modele: str = ""  # nom du fichier GGUF choisi au premier lancement
    modele_voix: str = "small"
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
        return cls(**connus)


def preparer_dossiers() -> None:
    for d in (DOSSIER_DONNEES, DOSSIER_MODELES, DOSSIER_DOCUMENTS):
        d.mkdir(parents=True, exist_ok=True)
