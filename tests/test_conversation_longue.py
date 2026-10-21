import copy
import threading

import httpx

from raya.app import Application
from raya.llm.agent import (AVIS_CONVERSATION_LONGUE, MAX_CARACTERES_HISTORIQUE, conversation_trop_longue,
                             dernier_echange)
from raya.stockage.historique import Historique


# Huit échanges de cette taille dépassent la limite ; un seul tient largement
TAILLE = MAX_CARACTERES_HISTORIQUE // 12


def echange(i: int, taille: int = TAILLE) -> list[dict]:
    return [{"role": "user", "content": f"Question {i} " + "x" * taille},
            {"role": "assistant", "content": f"Réponse {i} " + "y" * taille}]


def test_conversation_trop_longue():
    courte = echange(1) + [{"role": "user", "content": "Et ensuite ?"}]
    assert not conversation_trop_longue(courte)
    longue = [m for i in range(8) for m in echange(i)] + [{"role": "user", "content": "Et ensuite ?"}]
    assert conversation_trop_longue(longue)
    # Une seule demande, même très longue (texte collé), ne déclenche rien : il n'y a rien à recommencer
    assert not conversation_trop_longue([{"role": "user", "content": "z" * (MAX_CARACTERES_HISTORIQUE + 1)}])


def test_anciens_resultats_d_outils_comptent_raccourcis():
    # Un document de 4 000 caractères lu plus tôt ne compte plus que pour 1 500 : pas de nouvelle conversation
    messages = [{"role": "user", "content": "Lis le courrier"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "lire_document"}}]},
                {"role": "tool", "tool_call_id": "1", "content": "w" * 4000},
                {"role": "assistant", "content": "Voici le résumé."}]
    assert not conversation_trop_longue(messages * 3 + [{"role": "user", "content": "Et le montant ?"}])


def test_dernier_echange():
    messages = [*echange(1, 10),
                {"role": "user", "content": "Quel temps fait-il ?"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
                {"role": "tool", "tool_call_id": "1", "content": "Pluie à Lyon"},
                {"role": "assistant", "content": "Il pleut à Lyon."}]
    assert dernier_echange(messages) == [{"role": "user", "content": "Quel temps fait-il ?"},
                                         {"role": "assistant", "content": "Il pleut à Lyon."}]
    assert dernier_echange(echange(1, 5000)) == []  # trop long pour être repris
    assert dernier_echange([]) == []


def application(tmp_path, messages):
    app = Application.__new__(Application)
    app.historique = Historique(tmp_path / "h.sqlite")
    app._en_reponse = threading.Lock()
    app._messages = messages
    app._id_conversation = app.historique.enregistrer(None, app._messages)
    app.appels = appels = []
    app._js = lambda fonction, *args: appels.append((fonction, *copy.deepcopy(args)))  # copie, comme en JSON
    app._etat = lambda *args: None
    app._regarder_ecran = lambda texte: (None, "")
    app._resumer_en_arriere_plan = lambda: appels.append(("resume",))
    return app


def test_nouvelle_conversation_automatique(tmp_path):
    app = application(tmp_path, [m for i in range(8) for m in echange(i)])
    ancienne, appels = app._id_conversation, app.appels
    envoyes = []

    class AgentFactice:
        def repondre(self, messages, *args):
            envoyes.append(list(messages))
            return [{"role": "assistant", "content": "D'accord."}]

    app._agent = AgentFactice()
    app._repondre("Et ensuite ?", [], oral=False)

    # Le modèle ne reçoit que le dernier échange et la nouvelle demande
    assert envoyes[0] == [*echange(7), {"role": "user", "content": "Et ensuite ?"}]
    assert ("conversationRecommencee", envoyes[0], AVIS_CONVERSATION_LONGUE) in appels
    assert ("resume",) in appels
    # L'ancienne conversation reste dans la liste, la nouvelle est enregistrée à part
    assert app._id_conversation != ancienne and len(app.historique.lister()) == 2
    assert len(app.historique.charger(ancienne)) == 16


def test_demande_refusee_par_le_moteur(tmp_path):
    """L'estimation se trompe et le moteur refuse la demande (400) : nouvelle conversation, puis la réponse."""
    app = application(tmp_path, echange(1, 10) + echange(2, 10))
    envoyes = []

    class AgentFactice:
        def repondre(self, messages, *args):
            envoyes.append(list(messages))
            if len(envoyes) == 1:
                requete = httpx.Request("POST", "http://moteur")
                raise httpx.HTTPStatusError("400", request=requete, response=httpx.Response(400, request=requete))
            return [{"role": "assistant", "content": "D'accord."}]

    app._agent = AgentFactice()
    app._repondre("Et ensuite ?", [], oral=False)
    assert envoyes[1] == [*echange(2, 10), {"role": "user", "content": "Et ensuite ?"}]
    assert [a[0] for a in app.appels if a[0] in ("conversationRecommencee", "debutReponse", "erreurReponse")] == [
        "debutReponse", "conversationRecommencee", "debutReponse"]
    assert app._messages[-1] == {"role": "assistant", "content": "D'accord."}
