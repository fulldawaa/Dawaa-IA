"""Push-to-talk : touche globale (pynput) et enregistrement du micro (sounddevice)."""
import logging
import threading
from typing import Callable

import numpy as np
import sounddevice as sd
from pynput import keyboard

log = logging.getLogger(__name__)

FREQUENCE = 16_000  # Whisper attend du 16 kHz mono
DUREE_MIN = 0.4     # en dessous, on considère que c'est un appui accidentel
DUREE_MAX = 120

# Noms lisibles des touches proposées à l'utilisateur
NOMS_TOUCHES = {
    "ctrl_r": "Ctrl droit", "ctrl_l": "Ctrl gauche", "alt_r": "Alt Gr", "alt_l": "Alt",
    "shift_r": "Maj droite", "shift_l": "Maj gauche", "caps_lock": "Verr. Maj",
    "insert": "Inser", "pause": "Pause", "scroll_lock": "Arrêt défil", "menu": "Menu",
    "home": "Début", "end": "Fin", "page_up": "Page haut", "page_down": "Page bas",
    **{f"f{i}": f"F{i}" for i in range(1, 25)},
}


def nom_touche(touche) -> str | None:
    """Identifiant stable d'une touche pynput, ou None si elle n'est pas utilisable."""
    if isinstance(touche, keyboard.Key):
        return touche.name
    return None  # les lettres et chiffres sont exclus : on s'en sert pour écrire


def nom_lisible(identifiant: str) -> str:
    return NOMS_TOUCHES.get(identifiant, identifiant.replace("_", " ").capitalize())


def bip(montant: bool) -> None:
    """Petit son de début (aigu) ou de fin (grave) d'écoute."""
    try:
        frequence = 880 if montant else 600
        t = np.linspace(0, 0.09, int(22_050 * 0.09), False)
        onde = 0.2 * np.sin(2 * np.pi * frequence * t) * np.hanning(len(t))
        sd.play(onde.astype(np.float32), 22_050)
    except Exception:
        pass


class Enregistreur:
    def __init__(self):
        self._morceaux: list[np.ndarray] = []
        self._flux: sd.InputStream | None = None
        self._verrou = threading.Lock()

    @property
    def actif(self) -> bool:
        return self._flux is not None

    def demarrer(self) -> None:
        with self._verrou:
            if self._flux:
                return
            self._morceaux = []
            self._flux = sd.InputStream(samplerate=FREQUENCE, channels=1, dtype="float32", callback=self._recevoir)
            self._flux.start()

    def _recevoir(self, donnees, _frames, _temps, _statut) -> None:
        if sum(len(m) for m in self._morceaux) < FREQUENCE * DUREE_MAX:
            self._morceaux.append(donnees[:, 0].copy())

    def arreter(self) -> np.ndarray | None:
        """Arrête l'enregistrement ; renvoie l'audio, ou None s'il est trop court."""
        with self._verrou:
            if not self._flux:
                return None
            self._flux.stop()
            self._flux.close()
            self._flux = None
        if not self._morceaux:
            return None
        audio = np.concatenate(self._morceaux)
        return audio if len(audio) >= FREQUENCE * DUREE_MIN else None


class ToucheParler:
    """Écoute une touche globale : appui → `sur_appui`, relâchement → `sur_relache`."""

    def __init__(self, touche: str, sur_appui: Callable[[], None], sur_relache: Callable[[], None]):
        self.touche = touche
        self._sur_appui = sur_appui
        self._sur_relache = sur_relache
        self._enfoncee = False
        self._capture: Callable[[str], None] | None = None
        self._ecouteur = keyboard.Listener(on_press=self._appui, on_release=self._relache)
        self._ecouteur.daemon = True

    def demarrer(self) -> None:
        self._ecouteur.start()

    def capturer_prochaine_touche(self, rappel: Callable[[str], None]) -> None:
        """La prochaine touche spéciale pressée devient la touche « parler »."""
        self._capture = rappel

    def _appui(self, touche) -> None:
        nom = nom_touche(touche)
        if self._capture and nom and nom != "esc":
            rappel, self._capture = self._capture, None
            self.touche = nom
            rappel(nom)
            return
        if nom == self.touche and not self._enfoncee:  # ignore la répétition automatique
            self._enfoncee = True
            self._appeler(self._sur_appui)

    def _relache(self, touche) -> None:
        if nom_touche(touche) == self.touche and self._enfoncee:
            self._enfoncee = False
            self._appeler(self._sur_relache)

    @staticmethod
    def _appeler(fonction) -> None:
        try:
            fonction()
        except Exception:
            log.exception("Erreur dans le gestionnaire de touche")
