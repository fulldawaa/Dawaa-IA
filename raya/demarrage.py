"""Démarrer Raya avec Windows (pour que les rappels sonnent), sans droits administrateur.

Raya s'inscrit dans HKCU\\...\\Run et démarre alors discrètement, dans la barre près de l'horloge.
"""
import logging
import sys
import winreg

log = logging.getLogger(__name__)

CLE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOM = "Raya"
ARGUMENT = "--demarrage"


def commande() -> str | None:
    """Commande lancée par Windows ; None en développement (pas d'exe à inscrire)."""
    if not getattr(sys, "frozen", False):
        return None
    return f'"{sys.executable}" {ARGUMENT}'


def appliquer(actif: bool) -> None:
    """Inscrit ou retire Raya du démarrage de Windows."""
    cmd = commande()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_RUN, 0, winreg.KEY_SET_VALUE) as cle:
            if actif and cmd:
                winreg.SetValueEx(cle, NOM, 0, winreg.REG_SZ, cmd)
            elif not actif:
                try:
                    winreg.DeleteValue(cle, NOM)
                except FileNotFoundError:
                    pass
    except OSError:
        log.exception("Impossible de modifier le démarrage avec Windows")
    if actif and not cmd:
        log.info("Démarrage avec Windows ignoré en mode développement")


def lance_au_demarrage() -> bool:
    return ARGUMENT in sys.argv
