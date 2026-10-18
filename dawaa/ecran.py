"""« Regarde mon écran » : capture de l'écran, donnée au modèle local avec la demande.

La capture n'est jamais enregistrée : ni sur le disque, ni dans l'historique des conversations. Elle part seulement
vers le modèle qui tourne sur l'ordinateur, le temps d'une réponse.
"""
import base64
import io
import re

from PIL import Image, ImageGrab

# Côté le plus long de l'image envoyée : assez pour lire un message d'erreur, sans saturer la mémoire du modèle
TAILLE_MAX = 1280
QUALITE_JPEG = 85

_ECRAN = r"[ée]crans?"
# « regarde mon écran », « tu vois mon écran ? », « qu'est-ce qu'il y a sur l'écran », « fais une capture d'écran »
DEMANDE = re.compile(
    rf"\b(capture d'{_ECRAN}|copie d'{_ECRAN}|screenshot)\b"
    rf"|\b(regarde|regardez|regarder|vois|voyez|voir|lis|lisez|lire|montre|affich\w*|observe|analyse|explique|aide|"
    rf"qu'est-ce qu|qu'y a-t-il|il y a)\b.*\b{_ECRAN}\b"
    rf"|\b{_ECRAN}\b.*\b(regarde|regardez|regarder|vois|voyez|voir|lis|lisez|lire|observe|analyse|explique)\b", re.I)
# « lis le fichier qui est à l'écran » : c'est le fichier qu'il faut lire, pas une image de l'écran
DOCUMENT = re.compile(r"\b(fichiers?|documents?|tableaux?|excel|word|pdf)\b", re.I)


def demande_capture(texte: str) -> bool:
    return bool(DEMANDE.search(texte)) and not DOCUMENT.search(texte)


def capturer() -> bytes:
    """L'écran principal, réduit et compressé en JPEG."""
    image = ImageGrab.grab().convert("RGB")
    image.thumbnail((TAILLE_MAX, TAILLE_MAX), Image.Resampling.LANCZOS)
    tampon = io.BytesIO()
    image.save(tampon, "JPEG", quality=QUALITE_JPEG)
    return tampon.getvalue()


def en_url(image: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
