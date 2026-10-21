"""Point d'entrée de Raya."""
import ctypes
import logging
import logging.handlers
import sys
import threading

import webview

from raya import config, demarrage

log = logging.getLogger("raya")


def configurer_journal() -> None:
    config.DOSSIER_DONNEES.mkdir(parents=True, exist_ok=True)
    gestionnaire = logging.handlers.RotatingFileHandler(
        config.DOSSIER_DONNEES / "raya.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[gestionnaire],
                        format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    for bruyant in ("httpx", "httpcore", "primp", "faster_whisper", "pywebview"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)


def deja_ouvert() -> bool:
    """Empêche de lancer Raya deux fois (deux modèles chargés = PC saturé)."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\Raya_instance_unique")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def icone_notification(app, fenetre):
    """Icône près de l'horloge : la touche « parler » reste active quand la fenêtre est fermée."""
    import pystray
    from PIL import Image

    def ouvrir(_icone=None, _element=None):
        fenetre.show()
        fenetre.restore()

    def quitter(icone, _element=None):
        app.quitter_demande = True
        icone.stop()
        fenetre.destroy()

    image = Image.open(config.dossier_application() / "assets" / "raya.png")
    menu = pystray.Menu(
        pystray.MenuItem("Ouvrir Raya", ouvrir, default=True),
        pystray.MenuItem("Quitter Raya", quitter),
    )
    return pystray.Icon("Raya", image, "Raya — votre assistante", menu)


def main() -> None:
    renommes = config.reprendre_ancien_nom()
    configurer_journal()
    for dossier in renommes:
        log.info("Dossier de Dawaa repris : %s", dossier)
    if deja_ouvert():
        ctypes.windll.user32.MessageBoxW(
            None, "Raya est déjà ouverte.\n\nCliquez sur son icône près de l'horloge, en bas à droite de l'écran.",
            "Raya Assistant", 0x40)
        return

    from raya.app import Api, Application

    app = Application()
    fenetre = webview.create_window(
        "Raya Assistant",
        url=str(config.chemin_ui() / "index.html"),
        js_api=Api(app),
        width=1100, height=780, min_size=(720, 560),
        background_color="#F7F6F3",
        text_select=True,
        hidden=demarrage.lance_au_demarrage(),  # lancé avec Windows : discret, près de l'horloge
    )
    app.fenetre = fenetre
    icone = icone_notification(app, fenetre)
    app.notifier_windows = icone.notify
    premiere_fermeture = {"faite": False}

    def fermeture():
        if app.quitter_demande:
            return True
        fenetre.hide()
        if not premiere_fermeture["faite"]:
            premiere_fermeture["faite"] = True
            try:
                icone.notify("Raya reste disponible près de l'horloge. Clic droit sur l'icône → Quitter pour la fermer.",
                             "Raya Assistant")
            except Exception:
                pass
        return False  # on masque au lieu de fermer

    fenetre.events.closing += fermeture

    def au_demarrage():
        icone.run_detached()
        fenetre.events.loaded.wait(60)
        fenetre.events._pywebviewready.wait(30)
        threading.Thread(target=app.demarrer, daemon=True).start()

    webview.start(au_demarrage, private_mode=False, storage_path=str(config.DOSSIER_DONNEES / "webview"),
                  debug="--debug" in sys.argv)
    app.quitter_demande = True
    try:
        icone.stop()
    except Exception:
        pass
    if app._serveur:
        app._serveur.arreter()
    log.info("Raya fermé")


if __name__ == "__main__":
    main()
