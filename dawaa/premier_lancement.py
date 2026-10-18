"""Téléchargement des modèles au premier lancement (reprise possible, vérification SHA256)."""
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
import psutil

from dawaa import config

log = logging.getLogger(__name__)

HF = "https://huggingface.co"


@dataclass(frozen=True)
class Fichier:
    url: str
    destination: str  # relatif à DOSSIER_MODELES
    taille: int
    sha256: str = ""  # vide : on vérifie seulement la taille (petits fichiers de configuration)


MODELE_4B = "Qwen3.5-4B-Q4_K_M.gguf"
MODELE_2B = "Qwen3.5-2B-Q4_K_M.gguf"

MODELES_LLM = {
    MODELE_4B: Fichier(
        f"{HF}/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/{MODELE_4B}",
        MODELE_4B, 2_740_937_888, "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"),
    MODELE_2B: Fichier(
        f"{HF}/unsloth/Qwen3.5-2B-GGUF/resolve/f6d5376be1edb4d416d56da11e5397a961aca8ae/{MODELE_2B}",
        MODELE_2B, 1_280_835_840, "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"),
}

DOSSIER_WHISPER = "whisper-small"
_WHISPER = f"{HF}/Systran/faster-whisper-small/resolve/536b0662742c02347bc0e980a01041f333bce120"
FICHIERS_WHISPER = [
    Fichier(f"{_WHISPER}/config.json", f"{DOSSIER_WHISPER}/config.json", 2_370),
    Fichier(f"{_WHISPER}/tokenizer.json", f"{DOSSIER_WHISPER}/tokenizer.json", 2_203_239),
    Fichier(f"{_WHISPER}/vocabulary.txt", f"{DOSSIER_WHISPER}/vocabulary.txt", 459_861),
    Fichier(f"{_WHISPER}/model.bin", f"{DOSSIER_WHISPER}/model.bin", 483_546_902,
            "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
]


def choisir_modele() -> str:
    """4B si la machine a au moins ~8 Go de RAM, sinon 2B."""
    ram_go = psutil.virtual_memory().total / 1024**3
    return MODELE_4B if ram_go >= 7.5 else MODELE_2B


def fichiers_requis(modele: str) -> list[Fichier]:
    return [MODELES_LLM[modele], *FICHIERS_WHISPER]


def _complet(f: Fichier) -> bool:
    chemin = config.DOSSIER_MODELES / f.destination
    return chemin.is_file() and chemin.stat().st_size == f.taille


def manquants(modele: str) -> list[Fichier]:
    return [f for f in fichiers_requis(modele) if not _complet(f)]


def _sha256(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        while bloc := fichier.read(8 * 1024 * 1024):
            h.update(bloc)
    return h.hexdigest()


class ErreurTelechargement(Exception):
    pass


def telecharger(fichiers: list[Fichier], progression: Callable[[float, str], None],
                annule: Callable[[], bool] = lambda: False) -> None:
    """Télécharge les fichiers ; `progression(fraction, message)` est appelé régulièrement."""
    total = sum(f.taille for f in fichiers) or 1
    fait = 0
    for f in fichiers:
        destination = config.DOSSIER_MODELES / f.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        partiel = destination.with_name(destination.name + ".partiel")
        deja = partiel.stat().st_size if partiel.exists() else 0
        if deja > f.taille:
            partiel.unlink()
            deja = 0
        entetes = {"Range": f"bytes={deja}-"} if deja else {}
        try:
            with httpx.stream("GET", f.url, headers=entetes, follow_redirects=True,
                              timeout=httpx.Timeout(60, connect=20)) as r:
                if r.status_code == 200:
                    deja = 0  # le serveur ne gère pas la reprise : on recommence
                elif r.status_code != 206:
                    r.raise_for_status()
                fait_fichier = deja
                with open(partiel, "ab" if deja else "wb") as sortie:
                    for bloc in r.iter_bytes(1024 * 1024):
                        if annule():
                            raise ErreurTelechargement("Téléchargement interrompu.")
                        sortie.write(bloc)
                        fait_fichier += len(bloc)
                        progression((fait + fait_fichier) / total, "Téléchargement en cours…")
        except httpx.HTTPError as e:
            raise ErreurTelechargement(
                "Le téléchargement a été interrompu. Vérifiez votre connexion internet puis cliquez sur « Réessayer ». "
                "Ce qui a déjà été téléchargé est conservé.") from e
        if partiel.stat().st_size != f.taille:
            raise ErreurTelechargement("Le fichier téléchargé est incomplet. Cliquez sur « Réessayer ».")
        if f.sha256:
            progression((fait + f.taille) / total, "Vérification du fichier…")
            if _sha256(partiel) != f.sha256:
                partiel.unlink()
                raise ErreurTelechargement("Le fichier téléchargé est abîmé. Cliquez sur « Réessayer ».")
        partiel.replace(destination)
        fait += f.taille
        log.info("Téléchargé : %s", destination)
    progression(1.0, "Terminé")
