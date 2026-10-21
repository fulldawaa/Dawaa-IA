"""Synthèse vocale : voix Edge (internet), repli sur la voix Windows hors ligne.

Le texte arrive au fil de l'eau (streaming) : on le découpe en phrases, on synthétise
la phrase suivante pendant que la précédente est lue.
"""
import asyncio
import logging
import queue
import re
import threading
from typing import Callable

import miniaudio
import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

VOIX_DISPONIBLES = {
    "fr-FR-DeniseNeural": "Denise (femme)",
    "fr-FR-HenriNeural": "Henri (homme)",
    "fr-FR-VivienneMultilingualNeural": "Vivienne (femme)",
    "fr-FR-RemyMultilingualNeural": "Rémy (homme)",
}
FREQUENCE = 24_000
FIN_DE_PHRASE = re.compile(r"(?<=[.!?…:;])\s+|\n+")


def nettoyer_pour_voix(texte: str) -> str:
    """Retire ce qui ne se lit pas à voix haute : markdown, tableaux, adresses web, chemins."""
    lignes = []
    for ligne in texte.splitlines():
        if ligne.strip().startswith("|") or re.fullmatch(r"\s*[-=*_]{3,}\s*", ligne):
            continue  # tableaux et séparateurs : lus, ils sont incompréhensibles
        lignes.append(ligne)
    texte = "\n".join(lignes)
    texte = re.sub(r"```.*?```", " ", texte, flags=re.S)
    texte = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", texte)          # [texte](lien) → texte
    texte = re.sub(r"https?://\S+", "le lien affiché", texte)
    texte = re.sub(r"[A-Za-z]:\\[^\n]*?\.(docx|xlsx|pdf)", "le fichier", texte)
    texte = re.sub(r"`([^`]*)`", r"\1", texte)
    texte = re.sub(r"^\s*#{1,6}\s*", "", texte, flags=re.M)
    texte = re.sub(r"^\s*[-*•]\s+", "", texte, flags=re.M)
    texte = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", texte)
    texte = texte.replace(">", " ").replace("€", " euros")
    texte = re.sub(r"[ \t]+", " ", texte)
    return texte.strip()


def _synthese_edge(texte: str, voix: str) -> np.ndarray:
    import edge_tts

    async def produire() -> bytes:
        mp3 = b""
        async for morceau in edge_tts.Communicate(texte, voix).stream():
            if morceau["type"] == "audio":
                mp3 += morceau["data"]
        return mp3

    mp3 = asyncio.run(produire())
    if not mp3:
        raise RuntimeError("Aucun son reçu")
    son = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=FREQUENCE)
    return np.frombuffer(son.samples, dtype=np.int16)


class VoixWindows:
    """Voix hors ligne de Windows (SAPI)."""

    def __init__(self):
        self._moteur = None

    def dire(self, texte: str) -> None:
        import pyttsx3

        if self._moteur is None:
            self._moteur = pyttsx3.init()
            for v in self._moteur.getProperty("voices"):
                if "fr" in (v.id + v.name).lower() or "french" in v.name.lower():
                    self._moteur.setProperty("voice", v.id)
                    break
            self._moteur.setProperty("rate", 175)
        self._moteur.say(texte)
        self._moteur.runAndWait()

    def arreter(self) -> None:
        if self._moteur:
            try:
                self._moteur.stop()
            except Exception:
                pass


class Lecteur:
    """Lit le texte à voix haute, phrase par phrase, dans un fil d'exécution dédié."""

    def __init__(self, voix: str = "fr-FR-DeniseNeural",
                 sur_debut: Callable[[], None] = lambda: None, sur_fin: Callable[[], None] = lambda: None):
        self.voix = voix
        self._sur_debut = sur_debut
        self._sur_fin = sur_fin
        self._tampon = ""
        self._phrases: queue.Queue = queue.Queue()
        self._sons: queue.Queue = queue.Queue(maxsize=3)
        self._generation = 0
        self._hors_ligne = False
        self._windows = VoixWindows()
        self._occupe = threading.Event()
        threading.Thread(target=self._synthetiser, daemon=True).start()
        threading.Thread(target=self._jouer, daemon=True).start()

    # --- côté appelant ---

    @property
    def occupe(self) -> bool:
        return self._occupe.is_set()

    def ajouter(self, morceau: str) -> None:
        """Ajoute du texte reçu en streaming ; chaque phrase complète part en lecture."""
        self._tampon += morceau
        parties = FIN_DE_PHRASE.split(self._tampon)
        complet = " ".join(parties[:-1])
        if len(complet) >= 40:  # on regroupe les phrases très courtes pour une lecture plus fluide
            self._envoyer(complet)
            self._tampon = parties[-1]

    def terminer(self) -> None:
        if self._tampon.strip():
            self._envoyer(self._tampon)
        self._tampon = ""
        self._phrases.put((self._generation, None))  # marque de fin

    def dire(self, texte: str) -> None:
        self.arreter()
        self.ajouter(texte)
        self.terminer()

    def arreter(self) -> None:
        self._generation += 1
        self._tampon = ""
        sd.stop()
        self._windows.arreter()
        if self._occupe.is_set():
            self._occupe.clear()
            self._sur_fin()

    def _envoyer(self, texte: str) -> None:
        propre = nettoyer_pour_voix(texte)
        if re.search(r"\w", propre):
            self._phrases.put((self._generation, propre))

    # --- fils d'exécution ---

    def _synthetiser(self) -> None:
        while True:
            generation, texte = self._phrases.get()
            if generation != self._generation:
                continue
            if texte is None:
                self._sons.put((generation, None))
                continue
            son = None
            if not self._hors_ligne:
                try:
                    son = _synthese_edge(texte, self.voix)
                except Exception as e:
                    log.warning("Voix internet indisponible (%s) : passage à la voix Windows", e)
                    self._hors_ligne = True
                    threading.Timer(120, self._reessayer_internet).start()
            self._sons.put((generation, son if son is not None else texte))

    def _reessayer_internet(self) -> None:
        self._hors_ligne = False

    def _jouer(self) -> None:
        while True:
            generation, son = self._sons.get()
            if generation != self._generation:
                continue
            if son is None:
                if self._occupe.is_set():
                    self._occupe.clear()
                    self._sur_fin()
                continue
            if not self._occupe.is_set():
                self._occupe.set()
                self._sur_debut()
            try:
                if isinstance(son, str):
                    self._windows.dire(son)
                else:
                    sd.play(son, FREQUENCE)
                    sd.wait()
            except Exception:
                log.exception("Lecture audio impossible")
