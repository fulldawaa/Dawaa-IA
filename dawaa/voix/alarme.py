"""Sonnerie des rappels : un son d'alarme de Windows joué en boucle jusqu'à « J'ai compris » (1 minute au plus)."""
import logging
import os
import threading
import winsound
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

DOSSIER_SONS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Media"
# Sons d'alarme de l'application Horloge de Windows, présents sur Windows 10 et 11
SONS = {f"Alarm{n:02d}": f"Alarme {n}" for n in range(1, 11)}
SON_DEFAUT = "Alarm01"
DUREE_MAX = 60


def chemin_son(son: str) -> Path | None:
    chemin = DOSSIER_SONS / f"{son}.wav"
    return chemin if son in SONS and chemin.is_file() else None


class Alarme:
    def __init__(self):
        self._arret = threading.Event()
        self._verrou = threading.Lock()

    def sonner(self, son: str, ensuite: Callable[[], None] = lambda: None, duree_max: float = DUREE_MAX) -> None:
        """Fait sonner l'alarme en boucle (sans bloquer), puis appelle `ensuite` quand elle s'arrête.

        Sans son choisi (ou son introuvable), `ensuite` est appelé tout de suite.
        """
        chemin = chemin_son(son)
        if chemin is None:
            ensuite()
            return
        self.arreter()
        with self._verrou:
            self._arret = arret = threading.Event()
            try:
                winsound.PlaySound(str(chemin), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            except RuntimeError:
                log.exception("Alarme impossible")
                ensuite()
                return

        def attendre():
            arret.wait(duree_max)
            with self._verrou:
                if self._arret is arret:  # une alarme plus récente a pu prendre la suite
                    winsound.PlaySound(None, 0)
            ensuite()

        threading.Thread(target=attendre, daemon=True).start()

    def arreter(self) -> None:
        self._arret.set()

    @staticmethod
    def essayer(son: str) -> None:
        """Joue le son une fois (bouton « Écouter » des Réglages)."""
        if chemin := chemin_son(son):
            winsound.PlaySound(str(chemin), winsound.SND_FILENAME | winsound.SND_ASYNC)
