"""Boucle de conversation : envoie les messages au modèle, diffuse la réponse, exécute les outils."""
import json
import logging
import re
from datetime import datetime
from typing import Callable

import httpx

from dawaa import calcul, outils
from dawaa.outils import agenda as outil_agenda

log = logging.getLogger(__name__)

MAX_TOURS_OUTILS = 6
# ~8k tokens de contexte, dont ~3k pour le prompt, les outils et la mémoire :
# on garde environ 14 000 caractères d'historique
MAX_CARACTERES_HISTORIQUE = 14_000
MAX_CARACTERES_RESULTAT_ANCIEN = 1_500

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def prompt_systeme(contexte: str = "") -> str:
    maintenant = datetime.now()
    date = f"{JOURS[maintenant.weekday()]} {maintenant.day} {MOIS[maintenant.month - 1]} {maintenant.year}"
    return f"""Tu es Dawaa, un assistant sur l'ordinateur de l'utilisateur. Tu parles uniquement français.
L'utilisateur n'est pas à l'aise avec l'informatique.

Façon de parler :
- Phrases courtes et simples. Pas de jargon technique ; si un mot technique est inévitable, explique-le.
- Va droit au but. Pas de longues introductions.
- Vouvoie toujours l'utilisateur : dis « vous », jamais « tu » (sauf s'il demande le tutoiement).
- Si la demande n'est pas claire, pose UNE seule question précise.
- Les messages dictés à la voix contiennent parfois un mot mal reconnu qui se prononce presque pareil :
  comprends-le par le son avant de demander de reformuler (« et face la ligne » = « efface la ligne »,
  « et fesse-la » = « efface-la », « mais un minuteur » = « mets un minuteur »).
- Après une action réussie, termine par une phrase qui dit ce que tu as fait et où se trouve le résultat,
  avec l'« emplacement à annoncer » donné par l'outil (ex. : Documents > Dawaa > Lettre.docx).
  N'affiche jamais de chemin technique commençant par C:\\ : un bouton « Ouvrir » est déjà affiché sous ta réponse.

Règle absolue : un fichier n'existe que si tu as appelé l'outil qui le crée et qu'il a répondu sans erreur.
Ne dis JAMAIS qu'un fichier est créé, enregistré ou ouvert sans cela. Si l'utilisateur veut un fichier, appelle l'outil.

Ce que tu sais faire avec tes outils :
- Chercher sur internet (recherche_web, puis lire_page_web si besoin). Cite la source (le nom du site).
  Utilise-les pour toute information récente : actualités, météo, horaires, prix.
- Calculs : quand le programme te donne des « calculs exacts » (en bas de ces consignes), recopie ces résultats
  sans les changer. Sinon, pour un calcul compliqué, donne le résultat en précisant qu'il faut le vérifier.
- Rédiger, corriger, reformuler ou résumer un texte : fais-le directement dans ta réponse.
  N'utilise creer_document_word que si l'utilisateur veut un fichier Word.
- Lire un document Word, LibreOffice (.odt) ou PDF (lire_document).
- Fichiers de l'ordinateur (Bureau, Documents, Téléchargements, Images…) : pour « ouvre le fichier X »,
  appelle ouvrir_fichier (il affiche le fichier mais ne te donne pas son contenu) ; pour « lis », « lis-moi »,
  « que dit », « résume » le fichier X, appelle lire_document (ou tableau avec action=lire pour Excel).
  Donne le nom tel que l'utilisateur l'a dit, et le dossier seulement s'il l'a précisé (« sur mon bureau » → dossier=Bureau).
  Ne demande pas où se trouve le fichier : appelle directement l'outil, il cherche dans tous les dossiers.
  Si plusieurs fichiers correspondent, demande lequel en citant leurs noms.
- Tableaux Excel (outil tableau) : action=lire, creer, modifier, ou graphique pour y ajouter un graphique.
  Il lit aussi les anciens fichiers Excel (.xls), LibreOffice Calc (.ods) et CSV.
  Pour tout calcul sur un fichier Excel, utilise les résultats exacts donnés par action=lire : ne calcule jamais de tête.
- Quand un message contient « [Fichier joint : chemin] », utilise ce chemin exact avec les outils.
- Ouvrir un site dans le navigateur (ouvrir_site), ou directement une recherche sur YouTube, Google, Maps…
  Si l'outil propose un site sans l'ouvrir, dis lequel et demande confirmation : ne prétends pas l'avoir ouvert.
- Mémoire (outil memoire) : dès que l'utilisateur dit quelque chose de DURABLE sur lui (prénom, proches, ville,
  santé, habitudes, goûts, façon dont il veut que tu répondes, infos qu'il réutilisera), appelle memoire
  avec action=retenir, puis continue ta réponse normalement. S'il demande d'oublier quelque chose : action=oublier.
  Ne retiens jamais de mot de passe, code secret ou numéro bancaire.
- Agenda et rappels (outil agenda) : rendez-vous, rappels, médicaments, anniversaires. Pour quand, recopie
  EXACTEMENT les mots de l'utilisateur (« mardi à 15 h ») : ne calcule jamais de date toi-même. Après l'ajout,
  répète la date complète donnée par l'outil. Si l'utilisateur ne dit pas quel jour, demande-le d'abord.
  « Rappelle-moi… », « note… », « j'ai le coiffeur jeudi » → action=ajouter.
  « Qu'est-ce que j'ai demain ? » → action=lister. rappel_avant seulement si l'utilisateur dit « … avant ».
  Minuteur (« mets un minuteur de 10 minutes », « préviens-moi dans 20 minutes ») → action=ajouter, titre « Minuteur »
  (ou ce qu'il faut surveiller : « Pâtes »), quand = la durée dite par l'utilisateur. « Annule le minuteur » → supprimer.
  « Il reste combien de temps ? » : réponds avec le temps restant donné en bas de ces consignes.
- E-mails (outil email) : tu PRÉPARES le message, ouvert dans Gmail ou Outlook ; l'utilisateur le relit et
  clique lui-même sur Envoyer. destinataire = le nom dit par l'utilisateur (« Nicole » ; « envoie-moi » → « Moi ») :
  n'invente jamais d'adresse. S'il faut une date ou une heure (« la date du restaurant »), appelle d'abord agenda avec
  action=lister, sans la demander à l'utilisateur. Écris à la 1re personne, au nom de l'utilisateur : signe avec
  son prénom si tu le connais, sinon sans signature ; ne signe jamais « Dawaa ». Ton simple et chaleureux
  pour un proche (famille, ami), plus formel pour une administration ou une entreprise. Ne dis jamais qu'un e-mail est envoyé.
- Raccourcis (outil memoire) : si l'utilisateur veut garder ce qu'il vient de faire pour le refaire plus tard
  (« retiens ça sous le nom ma routine du matin »), appelle memoire avec action=enregistrer_raccourci et le nom.
  S'il demande un raccourci enregistré (« fais ma routine du matin »), appelle memoire avec action=lancer_raccourci.

Tu ne peux pas : envoyer un e-mail toi-même (tu le prépares seulement), acheter, remplir des formulaires sur internet, lancer des programmes,
supprimer ou déplacer des fichiers entiers, ni toucher aux réglages de l'ordinateur. Dis-le simplement si on te le demande.
Mais tu PEUX effacer une ligne ou une colonne d'un tableau, et le modifier : outil tableau, action=modifier
(supprimer_ligne, supprimer_colonne…), qui enregistre une copie.

Nous sommes le {date}. Les fichiers que tu crées sont rangés dans le dossier Documents > Dawaa.{contexte}"""


def bloc_memoire(souvenirs: str, resumes: list[tuple[float, str]], raccourcis: list[str] = (), prenom: str = "",
                 email_connu: bool = False) -> str:
    """Partie du prompt qui rappelle au modèle ce qu'il sait de l'utilisateur."""
    bloc = ""
    if prenom:
        bloc += (f"\n\nL'utilisateur s'appelle {prenom}. Appelle-le par son prénom de temps en temps, et signe ses "
                 f"e-mails « {prenom} ».")
    if email_connu:
        bloc += ("\n\nSon adresse e-mail est déjà dans le carnet. « Envoie-moi … par mail » : appelle tout de suite "
                 "email avec action=preparer et destinataire=« moi », sans rien lui demander.")
    if raccourcis:
        bloc += ("\n\nRaccourcis enregistrés par l'utilisateur (à lancer avec memoire, action=lancer_raccourci) : "
                 + ", ".join(f"« {r} »" for r in raccourcis) + ".")
    if souvenirs:
        bloc += ("\n\nCe que tu sais de l'utilisateur (retenu lors des conversations précédentes ; "
                 "ses préférences passent avant les consignes ci-dessus) :\n" + souvenirs)
    if resumes:
        lignes = []
        for horodatage, resume in resumes:
            d = datetime.fromtimestamp(horodatage)
            lignes.append(f"- {JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} : {resume}")
        bloc += "\n\nVos dernières conversations (pour t'en souvenir si l'utilisateur en parle) :\n" + "\n".join(lignes)
    if bloc:
        bloc += "\n\nRappel : vouvoie l'utilisateur, sauf si ses préférences ci-dessus demandent le tutoiement."
    return bloc


def bloc_fichiers_ouverts(fichiers: list[str]) -> str:
    """Partie du prompt qui dit au modèle quels documents l'utilisateur a ouverts à l'écran."""
    if not fichiers:
        return ""
    return ("\n\nDocuments ouverts à l'écran en ce moment (si l'utilisateur parle du fichier « ouvert », « que j'ai "
            "ouvert » ou « à l'écran », c'est l'un d'eux : lis-le avec tableau (action=lire) ou lire_document en donnant "
            "son nom, sans dossier) :\n" + "\n".join(f"- {f}" for f in fichiers))


PROMPT_RESUME = ("Résume cette conversation en UNE phrase de 25 mots maximum, en français, à la 3e personne : "
                 "ce que l'utilisateur voulait et ce qui a été fait (fichiers créés, sites, sujets). "
                 "Ne recopie aucun numéro, code ni mot de passe. Réponds uniquement par la phrase.")


# Garde-fou : le modèle annonce une action (fichier créé, site ouvert, info retenue) sans avoir appelé l'outil
OBJET_ANNONCE = re.compile(r"(\.docx|\.xlsx|fichier|document|site|page|mail|message|courriel)", re.I)
ACTION_ANNONCEE = re.compile(r"\b(créé|crée|enregistré|sauvegardé|ouvert|envoyé|préparé)e?s?\b", re.I)
DEMANDE_ACTION = re.compile(r"\b(word|excel|fichier|document|tableau|docx|xlsx|site|ouvre|ouvrir|youtube|"
                            r"mail|e-mail|email|courriel)\b", re.I)
MEMOIRE_ANNONCEE = re.compile(r"\b(j'ai (bien )?(retenu|noté|mémorisé|enregistré)|je (m'en souviendrai|retiens|note))\b", re.I)
CORRECTION_FICHIER = ("[Message automatique] Tu as annoncé une action (fichier créé, site ouvert ou information "
                      "retenue) sans appeler l'outil correspondant : elle n'a PAS été faite. Si l'utilisateur la veut, "
                      "appelle maintenant l'outil. Sinon, réponds sans prétendre l'avoir faite.")


# Garde-fou : le modèle demande où est un fichier, ou dit ne pas pouvoir le lire, au lieu d'appeler l'outil
QUESTION_EMPLACEMENT = re.compile(r"\b(où (il|elle) se trouve|où se trouve(-t-il|-t-elle)?|dans quel dossier|"
                                  r"je n'ai pas accès|je ne peux pas (lire|accéder|voir)|je n'arrive pas à (lire|accéder))\b",
                                  re.I)
CORRECTION_RECHERCHE = ("[Message automatique] Tu peux lire les fichiers de l'ordinateur : ne demande pas où se trouve "
                        "le fichier et ne dis pas que tu n'y as pas accès. Appelle maintenant tableau avec action=lire "
                        "(tableaux .xlsx, .xls, .ods, .csv) ou lire_document (Word, PDF, texte) avec son nom, sans dossier : l'outil "
                        "cherche dans tous ses dossiers. Si l'utilisateur veut seulement l'afficher, appelle ouvrir_fichier.")
# Garde-fou : le modèle demande une date qu'il pourrait trouver dans l'agenda
DEMANDE_DATE = re.compile(r"\b(date|heure|quand|prochain|prochaine)\b", re.I)
QUESTION_DATE = re.compile(r"\b(quel(le)?s? (est|sont) (la|les) (date|heure)s?|à quelle (date|heure)|quand (a|aura) lieu)\b", re.I)
CORRECTION_AGENDA = ("[Message automatique] Ne demande pas la date à l'utilisateur : cherche-la d'abord dans son agenda "
                     "(outil agenda, action=lister, periode=tout). Si elle n'y est pas, alors seulement demande-la.")
# Garde-fou : pour un e-mail, le modèle propose parfois un texte « à copier-coller » au lieu de l'outil
DEMANDE_EMAIL = re.compile(r"\b(envoie|envoyer|écris|ecris|écrire|prépare|rédige)\b.*\b(e-?mail|mail|courriel)s?\b", re.I)
# Seule réponse sans outil acceptable : demander une information qui manque (adresse, destinataire)
QUESTION_EMAIL = re.compile(r"(adresse|à qui|destinataire|quel(le)? est (son|sa|le|la) (nom|prénom))[^?]*\?", re.I)
POUR_MOI = re.compile(r"\b(envoie|envoyez|écris|ecris|écrivez)[- ]moi\b|\bm'envoyer\b|\bà moi\b|\bmoi[- ]même\b", re.I)
CORRECTION_EMAIL = ("[Message automatique] Tu peux préparer cet e-mail : appelle maintenant l'outil email avec "
                    "action=preparer (« envoie-moi » → destinataire « moi »). Il s'ouvre dans la messagerie de "
                    "l'utilisateur, qui l'envoie lui-même.")
# Garde-fou : le modèle dit avoir lancé un minuteur ou noté un rappel sans appeler l'outil agenda
DEMANDE_RAPPEL = re.compile(r"\b(minuteur|minuterie|compte à rebours|rappelle|rappelez|réveille|préviens|prévenez)", re.I)
RAPPEL_ANNONCE = re.compile(r"\b(lancé|programmé|réglé|activé|démarré|ajouté|noté|je vous (préviendrai|rappellerai))\b"
                            r"|\bva sonner\b|\bsonnera\b", re.I)
CORRECTION_RAPPEL = ("[Message automatique] Tu as annoncé un minuteur ou un rappel sans appeler l'outil agenda : il "
                     "n'existe PAS. Appelle maintenant agenda avec action=ajouter, un titre court et quand = les mots "
                     "exacts de l'utilisateur (« 10 minutes », « mardi à 15 h »).")
# Garde-fou : le modèle dit ne pas pouvoir modifier un tableau (il confond avec « supprimer un fichier »)
DEMANDE_TABLEAU = re.compile(r"\b(efface|effacer|supprime|supprimer|enlève|enlever|retire|retirer|ajoute|ajouter|"
                             r"trie|trier|modifie|modifier)\b.*\b(lignes?|colonnes?|cellules?|tableau)\b", re.I)
REFUS = re.compile(r"\b(je ne (peux|sais) pas|vous devez le faire|faites-le vous-même|il faut le faire vous-même)", re.I)
CORRECTION_TABLEAU = ("[Message automatique] Tu PEUX modifier ce tableau : appelle maintenant l'outil tableau avec "
                      'action=modifier et les modifications (ex. {"type": "supprimer_ligne", "ligne": 1}). '
                      "Une copie est enregistrée, l'original reste intact.")
CORRECTIONS = (CORRECTION_FICHIER, CORRECTION_RECHERCHE, CORRECTION_AGENDA, CORRECTION_EMAIL, CORRECTION_RAPPEL,
               CORRECTION_TABLEAU)


def annonce_sans_outil(demande: str, texte: str) -> bool:
    action = DEMANDE_ACTION.search(demande) and OBJET_ANNONCE.search(texte) and ACTION_ANNONCEE.search(texte)
    return bool(action or MEMOIRE_ANNONCEE.search(texte))


def correction_necessaire(demande: str, texte: str) -> str | None:
    """Message de correction à envoyer au modèle s'il a répondu sans appeler l'outil qu'il fallait."""
    if DEMANDE_RAPPEL.search(demande) and RAPPEL_ANNONCE.search(texte):
        return CORRECTION_RAPPEL
    if DEMANDE_TABLEAU.search(demande) and REFUS.search(texte):
        return CORRECTION_TABLEAU
    if annonce_sans_outil(demande, texte):
        return CORRECTION_FICHIER
    if DEMANDE_DATE.search(demande) and QUESTION_DATE.search(texte):
        return CORRECTION_AGENDA
    if DEMANDE_EMAIL.search(demande) and (POUR_MOI.search(demande) or not QUESTION_EMAIL.search(texte)):
        return CORRECTION_EMAIL
    if QUESTION_EMPLACEMENT.search(texte):
        return CORRECTION_RECHERCHE
    return None


def _sans_correction(messages: list[dict]) -> list[dict]:
    """Retire de l'historique la réponse erronée et le message de correction automatique."""
    resultat: list[dict] = []
    for m in messages:
        if m["role"] == "user" and m["content"] in CORRECTIONS:
            resultat.pop()  # la réponse erronée qui précède
        else:
            resultat.append(m)
    return resultat


def _taille(message: dict) -> int:
    return len(message.get("content") or "") + len(json.dumps(message.get("tool_calls") or ""))


def preparer_historique(messages: list[dict]) -> list[dict]:
    """Raccourcit l'historique pour tenir dans la mémoire du modèle (sans toucher à l'original)."""
    resultat = [dict(m) for m in messages]
    # 1. Les anciens résultats d'outils (sauf ceux du dernier échange) sont résumés
    dernier_user = max((i for i, m in enumerate(resultat) if m["role"] == "user"), default=0)
    for i, m in enumerate(resultat[:dernier_user]):
        if m["role"] == "tool" and len(m.get("content") or "") > MAX_CARACTERES_RESULTAT_ANCIEN:
            resultat[i]["content"] = m["content"][:MAX_CARACTERES_RESULTAT_ANCIEN] + " […]"
    # 2. On retire les échanges les plus anciens tant que c'est trop long
    while sum(map(_taille, resultat)) > MAX_CARACTERES_HISTORIQUE and len(resultat) > 1:
        resultat.pop(0)
        while resultat and resultat[0]["role"] != "user":
            resultat.pop(0)
    return resultat


class Agent:
    def __init__(self, url_serveur: str, contexte: Callable[[], str] = lambda: ""):
        self.url = url_serveur
        self.annule = False
        self._contexte = contexte  # souvenirs et résumés, relus à chaque requête

    def resumer(self, messages: list[dict]) -> str:
        """Résumé d'une conversation en une phrase (sans outils, sans streaming)."""
        transcription = "\n".join(
            f"{'Utilisateur' if m['role'] == 'user' else 'Assistant'} : {m['content'][:600]}"
            for m in messages if m["role"] in ("user", "assistant") and m.get("content"))
        r = httpx.post(f"{self.url}/v1/chat/completions", timeout=120, json={
            "messages": [{"role": "system", "content": PROMPT_RESUME},
                         {"role": "user", "content": transcription[-6000:]}],
            "temperature": 0.2,
            "max_tokens": 80,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip().split("\n")[0]

    def _flux(self, messages: list[dict], sur_texte: Callable[[str], None], supplement: str = "") -> dict:
        """Envoie la requête en streaming ; renvoie le message assistant complet.

        `supplement` complète le prompt pour cette demande seulement (calculs déjà faits)."""
        corps = {
            "messages": [{"role": "system", "content": prompt_systeme(self._contexte() + supplement)},
                         *preparer_historique(messages)],
            "tools": outils.SCHEMAS,
            "stream": True,
            "temperature": 0.4,
            "top_p": 0.9,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        contenu = ""
        appels: dict[int, dict] = {}
        with httpx.stream("POST", f"{self.url}/v1/chat/completions", json=corps, timeout=httpx.Timeout(600, connect=10)) as r:
            r.raise_for_status()
            for ligne in r.iter_lines():
                if self.annule:
                    break
                if not ligne.startswith("data:"):
                    continue
                donnees = ligne[5:].strip()
                if donnees == "[DONE]":
                    break
                try:
                    choix = json.loads(donnees)["choices"]
                except (ValueError, KeyError):
                    continue
                if not choix:
                    continue
                delta = choix[0].get("delta") or {}
                if morceau := delta.get("content"):
                    contenu += morceau
                    sur_texte(morceau)
                for tc in delta.get("tool_calls") or []:
                    appel = appels.setdefault(tc.get("index", 0), {"id": "", "type": "function",
                                                                   "function": {"name": "", "arguments": ""}})
                    appel["id"] = tc.get("id") or appel["id"]
                    fn = tc.get("function") or {}
                    appel["function"]["name"] += fn.get("name") or ""
                    appel["function"]["arguments"] += fn.get("arguments") or ""
        message = {"role": "assistant", "content": contenu}
        if appels:
            message["tool_calls"] = [appels[i] for i in sorted(appels)]
        return message

    def repondre(
        self,
        messages: list[dict],
        sur_texte: Callable[[str], None],
        sur_outil: Callable[[str], None] = lambda _: None,
        sur_effacer: Callable[[], None] = lambda: None,
    ) -> list[dict]:
        """Fait répondre le modèle à la suite de `messages`.

        Renvoie les nouveaux messages (assistant / tool) à ajouter à la conversation.
        `sur_effacer` est appelé quand le texte déjà affiché doit être retiré (réponse corrigée).
        """
        self.annule = False
        nouveaux: list[dict] = []
        deja_corrige = False
        derniere_demande = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        supplement = calcul.bloc_calculs(derniere_demande) + outil_agenda.bloc_minuteurs()
        for _ in range(MAX_TOURS_OUTILS):
            message = self._flux(messages + nouveaux, sur_texte, supplement)
            if (not self.annule and not message.get("tool_calls") and not deja_corrige
                    and not any(m["role"] == "tool" for m in nouveaux)
                    and (correction := correction_necessaire(derniere_demande, message["content"]))):
                # Le modèle prétend avoir agi, ou demande où est un fichier, sans appeler d'outil : on efface et on le relance
                log.warning("Réponse sans appel d'outil, relance : %s", message["content"][:200])
                deja_corrige = True
                sur_effacer()
                nouveaux.append(message)
                nouveaux.append({"role": "user", "content": correction})
                continue
            nouveaux.append(message)
            if self.annule or not message.get("tool_calls"):
                return _sans_correction(nouveaux)
            for appel in message["tool_calls"]:
                nom = appel["function"]["name"]
                sur_outil(outils.message_attente(nom, appel["function"]["arguments"]))
                log.info("Outil %s %s", nom, appel["function"]["arguments"])
                resultat = outils.executer(nom, appel["function"]["arguments"])
                log.info("→ %s", resultat[:300])
                nouveaux.append({"role": "tool", "tool_call_id": appel["id"], "content": resultat})
            if message["content"]:
                sur_texte("\n\n")
        # Trop d'allers-retours : on demande une réponse finale sans outil
        sur_texte("\n\n")
        nouveaux.append(self._flux(messages + nouveaux + [
            {"role": "user", "content": "Réponds maintenant à l'utilisateur avec ce que tu as, sans utiliser d'outil."}
        ], sur_texte, supplement))
        return _sans_correction(nouveaux)
