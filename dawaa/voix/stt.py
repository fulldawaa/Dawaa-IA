"""Reconnaissance vocale locale (faster-whisper)."""
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class Transcripteur:
    def __init__(self, dossier_modele: Path):
        from faster_whisper import WhisperModel  # import lourd : seulement quand on en a besoin

        self._modele = WhisperModel(str(dossier_modele), device="cpu", compute_type="int8")

    def transcrire(self, audio: np.ndarray) -> str:
        segments, _ = self._modele.transcribe(
            audio,
            language="fr",
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        texte = " ".join(s.text.strip() for s in segments).strip()
        log.info("Transcription : %s", texte)
        return texte
