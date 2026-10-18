import hashlib

import httpx
import pytest

from dawaa import config, premier_lancement as pl


@pytest.fixture
def modeles(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DOSSIER_MODELES", tmp_path / "modeles")
    return tmp_path / "modeles"


def _serveur(contenu: bytes, coupure: int | None = None):
    """Faux serveur HTTP qui gère les requêtes « Range » (reprise)."""
    def repondre(requete: httpx.Request) -> httpx.Response:
        debut = 0
        if plage := requete.headers.get("Range"):
            debut = int(plage.split("=")[1].rstrip("-"))
        corps = contenu[debut:coupure] if coupure else contenu[debut:]
        return httpx.Response(206 if debut else 200, content=corps)
    return httpx.MockTransport(repondre)


def _brancher(monkeypatch, transport):
    monkeypatch.setattr(pl.httpx, "stream",
                        lambda *a, **k: httpx.Client(transport=transport).stream(*a[:2], headers=k.get("headers")))


def test_telechargement_reprise_et_verification(modeles, monkeypatch):
    contenu = b"x" * 3000 + b"y" * 3000
    f = pl.Fichier("https://exemple/modele.gguf", "modele.gguf", len(contenu), hashlib.sha256(contenu).hexdigest())
    # 1er essai : la connexion coupe à la moitié → fichier incomplet
    _brancher(monkeypatch, _serveur(contenu, coupure=3000))
    with pytest.raises(pl.ErreurTelechargement):
        pl.telecharger([f], lambda *_: None)
    assert (modeles / "modele.gguf.partiel").stat().st_size == 3000
    # 2e essai : reprise là où on s'était arrêté
    etapes = []
    _brancher(monkeypatch, _serveur(contenu))
    pl.telecharger([f], lambda fraction, msg: etapes.append(fraction))
    assert (modeles / "modele.gguf").read_bytes() == contenu
    assert etapes == sorted(etapes) and etapes[-1] == 1.0  # la barre n'avance que dans un sens


def test_fichier_abime_est_supprime(modeles, monkeypatch):
    contenu = b"abc" * 100
    f = pl.Fichier("https://exemple/m.bin", "m.bin", len(contenu), "0" * 64)
    _brancher(monkeypatch, _serveur(contenu))
    with pytest.raises(pl.ErreurTelechargement, match="abîmé"):
        pl.telecharger([f], lambda *_: None)
    assert not (modeles / "m.bin.partiel").exists()


def test_choix_du_modele_selon_la_ram(monkeypatch):
    class Memoire:
        def __init__(self, go): self.total = go * 1024**3
    monkeypatch.setattr(pl.psutil, "virtual_memory", lambda: Memoire(16))
    assert pl.choisir_modele() == pl.MODELE_4B
    monkeypatch.setattr(pl.psutil, "virtual_memory", lambda: Memoire(7.8))
    assert pl.choisir_modele() == pl.MODELE_4B
    monkeypatch.setattr(pl.psutil, "virtual_memory", lambda: Memoire(4))
    assert pl.choisir_modele() == pl.MODELE_2B
