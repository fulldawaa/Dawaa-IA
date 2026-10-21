from raya.llm.agent import CORRECTION_NUMERO, Agent, numero_invente

RESULTAT_WEB = ("Résultats pour « mairie de Roanne téléphone » :\n1. Mairie de Roanne\n"
                "   Accueil : 04.77.23.20.00, du lundi au vendredi\n   Source : https://www.roanne.fr")


def test_numero_invente_sans_source():
    demande = [{"role": "user", "content": "Quel est le numéro de la mairie de Roanne ?"}]
    assert numero_invente("Vous pouvez appeler le 04 77 12 34 56.", demande)
    assert numero_invente("Appelez le +33 4 77 12 34 56.", demande)


def test_numero_trouve_par_la_recherche():
    messages = [{"role": "user", "content": "Quel est le numéro de la mairie de Roanne ?"},
                {"role": "tool", "tool_call_id": "1", "content": RESULTAT_WEB}]
    # Même numéro, écrit autrement
    assert not numero_invente("D'après roanne.fr, appelez le 04 77 23 20 00.", messages)
    assert not numero_invente("Appelez le +33 (0)4 77 23 20 00.", messages)
    assert numero_invente("Appelez le 04 77 23 20 01.", messages)


def test_numero_dit_par_l_utilisateur_ou_retenu():
    messages = [{"role": "user", "content": "Le numéro de ma fille est le 06 12 34 56 78, appelle-la"}]
    assert not numero_invente("Le numéro de votre fille est le 06 12 34 56 78.", messages)
    assert not numero_invente("Votre médecin : 01 45 67 89 10.", [], contexte="- Médecin traitant : 0145678910")
    # Un numéro donné plus tôt par l'assistant lui-même n'est pas une source
    assert numero_invente("C'est le 01 23 45 67 89.", [{"role": "assistant", "content": "01 23 45 67 89"}])


def test_pas_de_faux_positif():
    rien = [{"role": "user", "content": "Bonjour"}]
    for texte in ("En cas d'urgence, appelez le 15, le 18 ou le 112.", "La maison coûte 250 000 euros.",
                  "Nous sommes le 21 octobre 2026.", "Il y a 67 000 habitants à Roanne."):
        assert not numero_invente(texte, rien)


def test_relance_si_numero_invente(monkeypatch):
    agent = Agent("http://serveur")
    reponses = iter([{"role": "assistant", "content": "Le numéro de la mairie est le 04 77 12 34 56."},
                     {"role": "assistant", "content": "Je n'ai pas trouvé ce numéro."}])
    envoyes = []
    monkeypatch.setattr(agent, "_flux", lambda messages, *_: envoyes.append(messages) or next(reponses))
    effaces = []
    nouveaux = agent.repondre([{"role": "user", "content": "Quel est le numéro de la mairie ?"}],
                              lambda _: None, sur_effacer=lambda: effaces.append(True))
    assert effaces and envoyes[1][-1]["content"] == CORRECTION_NUMERO
    # La réponse inventée et la correction ne restent pas dans l'historique
    assert nouveaux == [{"role": "assistant", "content": "Je n'ai pas trouvé ce numéro."}]
