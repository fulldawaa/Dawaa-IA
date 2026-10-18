"""Reconnaissance vocale locale (faster-whisper)."""
import logging
import re
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Phrases d'exemple données à Whisper comme « texte déjà entendu » : il reconnaît beaucoup mieux ces mots.
# Sans elles, « efface la première ligne » devient « et face la première ligne » et « envoie un mail à Nicole »
# devient « au revoir, amie folle ». Des phrases complètes marchent mieux qu'une liste de mots.
VOCABULAIRE = ("Efface la première ligne. Efface-la. Supprime la colonne. Ajoute une ligne au tableau. "
               "Mets un minuteur de 10 minutes. Rappelle-moi le dentiste. Lis-moi le courrier. "
               "Ouvre le fichier sur mon bureau. Envoie un mail.")
MAX_NOMS = 20
# Phrases que Whisper invente sur du bruit (apprises sur des sous-titres de vidéos)
HALLUCINATION = re.compile(r"sous-titr|amara\.org|merci d'avoir regardé|abonnez-vous", re.I)
# Confusions restantes, quand la phrase commence par un « efface » mal entendu
_COMMANDE_EFFACE = re.compile(r"^(?:et|é|eh|ai|aie|hé)[ -]?(?:faces?|fasses?|fesses?|faises?)"
                              r"(?=[ -](?:la|le|les|l'|leu|tout|ça|ca|cette|ce|ces)\b|[ .!?]*$)", re.I)


def corriger(texte: str) -> str:
    """Retire les phrases inventées et corrige les « efface » mal entendus."""
    if HALLUCINATION.search(texte):
        log.info("Transcription ignorée (phrase inventée par Whisper) : %s", texte)
        return ""
    texte = _COMMANDE_EFFACE.sub("Efface", texte.strip())
    return re.sub(r"\b(efface)[- ]leu\b", r"\1-le", texte, flags=re.I)


def vocabulaire(noms: list[str] = ()) -> str:
    """Le texte guide, avec le prénom de l'utilisateur et les noms de ses contacts."""
    noms = [n.strip() for n in noms if n and n.strip()][:MAX_NOMS]
    return VOCABULAIRE + (f" Noms : {', '.join(noms)}." if noms else "")


class Transcripteur:
    def __init__(self, dossier_modele: Path):
        from faster_whisper import WhisperModel  # import lourd : seulement quand on en a besoin

        self._modele = WhisperModel(str(dossier_modele), device="cpu", compute_type="int8")

    def transcrire(self, audio: np.ndarray, noms: list[str] = ()) -> str:
        segments, _ = self._modele.transcribe(
            audio,
            language="fr",
            beam_size=5,
            vad_filter=True,  # indispensable avec le texte guide : sur du silence, Whisper l'inventerait
            condition_on_previous_text=False,
            initial_prompt=vocabulaire(noms),
        )
        texte = corriger(" ".join(s.text.strip() for s in segments).strip())
        log.info("Transcription : %s", texte)
        return texte
