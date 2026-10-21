import io

import pytest
from PIL import Image

from raya import ecran, premier_lancement
from raya.llm import agent as agent_module
from raya.llm.agent import Agent
from raya.llm.serveur import ServeurLLM


@pytest.mark.parametrize("texte", [
    "Regarde mon écran", "Tu vois mon écran ?", "Qu'est-ce qu'il y a sur mon écran ?", "Fais une capture d'écran",
    "Aide-moi avec le message affiché à l'écran", "Regarde l'écran et dis-moi où cliquer",
    "mon écran est tout noir, tu peux regarder ?",
])
def test_demandes_de_capture(texte):
    assert ecran.demande_capture(texte)


@pytest.mark.parametrize("texte", [
    "Lis le fichier qui est à l'écran",  # c'est le fichier qu'il faut lire
    "Résume le document ouvert à l'écran", "J'ai acheté un nouvel écran", "Règle la luminosité de l'écran",
    "regarde ça",
])
def test_pas_de_capture(texte):
    assert not ecran.demande_capture(texte)


def test_capture_reduite(monkeypatch):
    monkeypatch.setattr(ecran.ImageGrab, "grab", lambda: Image.new("RGBA", (2560, 1440), "white"))
    image = Image.open(io.BytesIO(ecran.capturer()))
    assert image.format == "JPEG" and image.size == (1280, 720)
    assert ecran.en_url(b"abc") == "data:image/jpeg;base64,YWJj"


def test_image_jointe_a_la_demande_seulement(monkeypatch):
    """L'image part avec la dernière demande, mais ne revient pas dans les messages à enregistrer."""
    envoyes = []

    def faux_flux(self, messages, sur_texte, supplement=""):
        envoyes.append((messages, supplement))
        return {"role": "assistant", "content": "Je vois une fenêtre d'erreur."}

    monkeypatch.setattr(Agent, "_flux", faux_flux)
    messages = [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Bonjour !"},
                {"role": "user", "content": "Regarde mon écran"}]
    nouveaux = Agent("http://x").repondre(messages, lambda _: None, image=b"jpeg")
    (envoye, supplement), = envoyes
    assert envoye[0] == messages[0]
    texte, image = envoye[-1]["content"]
    assert texte == {"type": "text", "text": "Regarde mon écran"}
    assert image["image_url"]["url"] == "data:image/jpeg;base64,anBlZw=="
    assert agent_module.CONSIGNE_ECRAN in supplement
    assert messages[-1]["content"] == "Regarde mon écran"  # la conversation enregistrée reste du texte
    assert nouveaux == [{"role": "assistant", "content": "Je vois une fenêtre d'erreur."}]


def test_vue_telechargee_avec_le_modele(tmp_path, monkeypatch):
    monkeypatch.setattr(premier_lancement.config, "DOSSIER_MODELES", tmp_path)
    for modele in (premier_lancement.MODELE_4B, premier_lancement.MODELE_2B):
        assert premier_lancement.VISION[modele] in premier_lancement.fichiers_requis(modele)
    assert premier_lancement.chemin_vision(premier_lancement.MODELE_4B) is None  # pas encore téléchargée
    vue = premier_lancement.VISION[premier_lancement.MODELE_4B]
    with open(tmp_path / vue.destination, "wb") as f:
        f.truncate(vue.taille)
    assert premier_lancement.chemin_vision(premier_lancement.MODELE_4B) == tmp_path / vue.destination


def test_serveur_charge_la_vue(tmp_path, monkeypatch):
    lances = []
    for nom in ("llama-server.exe", "modele.gguf", "vue.gguf"):
        (tmp_path / nom).touch()
    from raya.llm import serveur
    monkeypatch.setattr(serveur, "chemin_llama_server", lambda: tmp_path / "llama-server.exe")
    monkeypatch.setattr(serveur.subprocess, "Popen", lambda cmd, **_: lances.append(cmd))
    monkeypatch.setattr(serveur, "_lier_a_raya", lambda _: None)
    monkeypatch.setattr(ServeurLLM, "_attendre_pret", lambda *_: None)
    ServeurLLM(tmp_path / "modele.gguf", tmp_path / "vue.gguf").demarrer()
    ServeurLLM(tmp_path / "modele.gguf").demarrer()
    assert "--mmproj" in lances[0] and str(tmp_path / "vue.gguf") in lances[0]
    assert "--mmproj" not in lances[1]
