"""Cœur de l'application : relie l'interface (JS), le modèle, la voix et l'historique."""
import ctypes
import json
import logging
import os
import re
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import httpx
import webview
from webview.dom import DOMEventHandler

from raya import accueil, config, dates, demarrage, ecran, premier_lancement
from raya.config import Reglages
from raya.llm.agent import (AVIS_CONVERSATION_LONGUE, Agent, bloc_fichiers_ouverts, bloc_memoire,
                             conversation_trop_longue, dernier_echange)
from raya.llm.serveur import ServeurLLM
from raya import outils
from raya.outils import agenda as outil_agenda
from raya.outils import email as outil_email
from raya.outils import carnet, navigation, ordinateur, souvenirs
from raya.outils.fichiers import MARQUE_CHEMIN
from raya.stockage.agenda import Agenda
from raya.stockage.historique import Historique
from raya.stockage.memoire import Memoire
from raya.stockage.sensible import masquer
from raya.voix.alarme import SONS, Alarme
from raya.voix.ecoute import Enregistreur, ToucheParler, bip, nom_lisible
from raya.voix.tts import VOIX_DISPONIBLES, Lecteur

log = logging.getLogger(__name__)

EXTENSIONS_JOINTES = {".docx", ".odt", ".pdf", ".txt", ".md", ".xlsx", ".xlsm", ".xls", ".ods", ".csv"}
FICHIER_RESULTAT = re.compile(re.escape(MARQUE_CHEMIN) + r"(.+?\.(?:docx|xlsx|xlsm))")
SOUVENIR_RESULTAT = re.compile(r"\[souvenir n°(\d+)\] : (.+)")
PROPOSITION_RESULTAT = re.compile(r"\[proposition de site : (\S+) \| ([^\]]*)\]")


def elements_a_afficher(nouveaux: list[dict]) -> dict:
    """Ce que l'interface affiche sous la réponse : fichiers créés, souvenirs retenus, sites proposés."""
    fichiers, souvenirs_, propositions = [], [], []
    for m in nouveaux:
        if m["role"] != "tool":
            continue
        fichiers += [c for c in FICHIER_RESULTAT.findall(m["content"]) if Path(c).exists()]
        souvenirs_ += [{"id": int(i), "texte": t.strip()} for i, t in SOUVENIR_RESULTAT.findall(m["content"])]
        propositions += [{"url": u, "titre": t.strip(), "domaine": navigation.domaine(u)}
                         for u, t in PROPOSITION_RESULTAT.findall(m["content"])]
    return {"fichiers": list(dict.fromkeys(fichiers)), "souvenirs": souvenirs_, "propositions": propositions[-1:]}


class Application:
    def __init__(self):
        self.reglages = Reglages.charger()
        self.historique = Historique()
        self.memoire = Memoire()
        self.agenda = Agenda()
        souvenirs.configurer(self.memoire)
        navigation.configurer(self.memoire)
        outil_agenda.configurer(self.agenda)
        outil_email.configurer(self.memoire, lambda: self.reglages.messagerie)
        carnet.configurer(self.memoire)
        self.notifier_windows = None  # bulle près de l'horloge, fournie par main.py
        self.alarme = Alarme()
        self._resume_en_cours = threading.Lock()
        self.fenetre: webview.Window | None = None
        self.quitter_demande = False

        self._serveur: ServeurLLM | None = None
        self._agent: Agent | None = None
        self._transcripteur = None
        self._touche: ToucheParler | None = None
        self._enregistreur = Enregistreur()
        self._lecteur = Lecteur(self.reglages.voix, sur_debut=lambda: self._etat("parle"),
                                sur_fin=lambda: self._etat("pret") if self._pret else None)

        self._pret = False
        self._en_reponse = threading.Lock()
        self._messages: list[dict] = []
        self._id_conversation: int | None = None
        self._telechargement = threading.Event()
        self._annuler_telechargement = False

    # ---------- communication vers l'interface ----------

    def _js(self, fonction: str, *args) -> None:
        if not self.fenetre:
            return
        arguments = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        try:
            self.fenetre.run_js(f"window.raya && raya.{fonction}({arguments})")
        except Exception:
            log.debug("Appel JS impossible : %s", fonction, exc_info=True)

    def _etat(self, etat: str, detail: str = "") -> None:
        self._js("etat", etat, detail, nom_lisible(self.reglages.touche_parler))

    # ---------- démarrage ----------

    def demarrer(self) -> None:
        """Appelé dans un fil séparé une fois la fenêtre affichée."""
        try:
            config.preparer_dossiers()
            demarrage.appliquer(self.reglages.demarrer_avec_windows)
            threading.Thread(target=self._surveiller_rappels, daemon=True).start()
            self._installer_glisser_deposer()
            self._js("appliquerReglages", self._reglages_pour_ui())
            self._js("listeConversations", self.historique.lister())
            modele = self.reglages.modele or premier_lancement.choisir_modele()
            if premier_lancement.manquants(modele):
                self._premier_lancement(modele)  # l'accueil s'ouvre pendant le téléchargement
            elif not self.reglages.accueil_fait:
                self._js("ouvrirAccueil", 1)
            if self.reglages.modele != modele:
                self.reglages.modele = modele
                self.reglages.enregistrer()
            self._etat("demarrage", "Je me prépare, quelques secondes…")
            chargement_voix = threading.Thread(target=self._charger_voix, daemon=True)
            chargement_voix.start()
            self._serveur = ServeurLLM(config.DOSSIER_MODELES / modele, premier_lancement.chemin_vision(modele))
            self._serveur.demarrer()
            self._agent = Agent(self._serveur.url, contexte=self._contexte_memoire)
            chargement_voix.join()
            self._pret = True
            self._etat("pret")
            # Lancée avec Windows, Raya reste discrète près de l'horloge : pas de voix surprise à l'allumage
            if self.reglages.accueil_fait and not demarrage.lance_au_demarrage():
                self._lecteur.dire(accueil.salutation(self.reglages.prenom, datetime.now()))
            self._resumer_en_arriere_plan()
        except Exception as e:
            log.exception("Échec du démarrage")
            self._etat("erreur", f"Raya n'a pas pu démarrer : {e}. Fermez puis relancez le programme.")

    def _charger_voix(self) -> None:
        try:
            from raya.voix.stt import Transcripteur

            self._transcripteur = Transcripteur(config.DOSSIER_MODELES / premier_lancement.DOSSIER_WHISPER)
            self._touche = ToucheParler(self.reglages.touche_parler, self._appui_parler, self._relache_parler)
            self._touche.demarrer()
        except Exception:
            log.exception("Reconnaissance vocale indisponible")
            self._js("notification", "La reconnaissance vocale n'a pas pu démarrer. Vous pouvez toujours écrire.")

    def _premier_lancement(self, modele: str) -> None:
        fichiers = premier_lancement.manquants(modele)
        taille_go = sum(f.taille for f in fichiers) / 1e9
        # Raya déjà installée avant l'arrivée de « regarde mon écran » : il ne manque que la vue
        mise_a_jour = fichiers == [premier_lancement.VISION[modele]]
        self._js("premierLancement", round(taille_go, 1), mise_a_jour)
        while True:
            self._telechargement.wait()
            self._telechargement.clear()
            try:
                premier_lancement.telecharger(
                    premier_lancement.manquants(modele),
                    lambda fraction, message: self._js("progression", fraction, message),
                    annule=lambda: self._annuler_telechargement or self.quitter_demande,
                )
                self._js("finPremierLancement")
                return
            except premier_lancement.ErreurTelechargement as e:
                if self.quitter_demande:
                    raise
                self._js("erreurTelechargement", str(e))

    def _installer_glisser_deposer(self) -> None:
        def deposer(evenement):
            chemins = [f.get("pywebviewFullPath") for f in evenement.get("dataTransfer", {}).get("files", [])]
            self._joindre([c for c in chemins if c])

        self.fenetre.dom.document.events.drop += DOMEventHandler(deposer, prevent_default=True, stop_propagation=True)

    def _joindre(self, chemins: list[str]) -> None:
        acceptes = [c for c in chemins if Path(c).suffix.lower() in EXTENSIONS_JOINTES]
        if len(acceptes) < len(chemins):
            self._js("notification", "Je sais lire les fichiers Word, LibreOffice (.odt, .ods), PDF, Excel, CSV et texte uniquement.")
        for c in acceptes:
            self._js("fichierJoint", c, Path(c).name)

    # ---------- conversation ----------

    def envoyer(self, texte: str, fichiers: list[str], oral: bool = False) -> None:
        if not self._pret or not self._agent:
            self._js("notification", "Je suis encore en train de démarrer, un instant…")
            return
        threading.Thread(target=self._repondre, args=(texte, fichiers, oral), daemon=True).start()

    def _repondre(self, texte: str, fichiers: list[str], oral: bool) -> None:
        if not self._en_reponse.acquire(timeout=30):
            self._js("notification", "Je termine ma réponse précédente, réessayez dans un instant.")
            return
        try:
            contenu = texte.strip()
            for f in fichiers:
                contenu += f"\n[Fichier joint : {f}]"
            self._messages.append({"role": "user", "content": contenu})
            recommencee = conversation_trop_longue(self._messages)
            if recommencee:
                self._recommencer_conversation()
            navigation.contexte.derniere_demande = texte
            image, consigne = self._regarder_ecran(texte)
            self._etat("reflechit")
            self._js("debutReponse")
            if oral:
                self._lecteur.arreter()
                if recommencee:
                    self._lecteur.ajouter(AVIS_CONVERSATION_LONGUE + "\n")
            tampon = {"texte": "", "envoi": time.monotonic()}

            def vider():
                if tampon["texte"]:
                    self._js("ajouterTexte", tampon["texte"])
                    tampon["texte"] = ""
                tampon["envoi"] = time.monotonic()

            def sur_texte(morceau: str):
                tampon["texte"] += morceau
                if time.monotonic() - tampon["envoi"] > 0.05:
                    vider()
                if oral:
                    self._lecteur.ajouter(morceau)

            def sur_outil(message: str):
                vider()
                self._etat("outil", message)

            def sur_effacer():
                tampon["texte"] = ""
                self._js("effacerReponse")
                if oral:
                    self._lecteur.arreter()

            nouveaux = None
            while nouveaux is None:
                try:
                    nouveaux = self._agent.repondre(self._messages, sur_texte, sur_outil, sur_effacer, image, consigne)
                except httpx.HTTPError as e:
                    # Malgré l'estimation, la demande dépasse la mémoire du modèle (le moteur répond 400) :
                    # on recommence une conversation plutôt que d'afficher une erreur
                    refusee = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 400
                    if refusee and not recommencee and len(self._messages) > 1:
                        log.warning("Demande refusée par le moteur, nouvelle conversation : %s", e.response.text[:200])
                        recommencee = True
                        tampon["texte"] = ""
                        self._recommencer_conversation()
                        self._js("debutReponse")
                        if oral:
                            self._lecteur.arreter()
                            self._lecteur.ajouter(AVIS_CONVERSATION_LONGUE + "\n")
                        continue
                    log.exception("Erreur du moteur IA")
                    vider()
                    self._messages.pop()
                    self._js("erreurReponse", "Désolé, je n'ai pas pu répondre. Réessayez dans un instant.")
                    self._redemarrer_moteur_si_besoin()
                    return
            vider()
            self._messages += nouveaux
            self._js("finReponse", elements_a_afficher(nouveaux))
            self._id_conversation = self.historique.enregistrer(self._id_conversation, self._messages)
            self._js("listeConversations", self.historique.lister())
            if recommencee:
                self._resumer_en_arriere_plan()  # Raya se souviendra de l'essentiel de l'ancienne conversation
            if oral:
                self._lecteur.terminer()
            if not (oral and self._lecteur.occupe):
                self._etat("pret")
        finally:
            self._en_reponse.release()

    def _recommencer_conversation(self) -> None:
        """Conversation trop longue pour le modèle : la demande part dans une nouvelle conversation, avec le
        dernier échange pour garder le fil. L'ancienne reste enregistrée dans la liste."""
        log.info("Conversation trop longue : nouvelle conversation")
        self._messages = [*dernier_echange(self._messages[:-1]), self._messages[-1]]
        self._id_conversation = None
        self._js("conversationRecommencee", self._messages, AVIS_CONVERSATION_LONGUE)

    def _regarder_ecran(self, texte: str) -> tuple[bytes | None, str]:
        """« Regarde mon écran » : capture à joindre à la demande, ou consigne si c'est impossible."""
        if not ecran.demande_capture(texte):
            return None, ""
        if not self._serveur.vision:
            return None, ("\n\nL'utilisateur demande de regarder son écran, mais ta vue n'est pas encore installée : "
                          "dis-lui de fermer puis relancer Raya, qui la téléchargera (environ 0,7 Go).")
        self._etat("outil", "Je regarde votre écran…")
        cachee = self._cacher_fenetre()
        try:
            return ecran.capturer(), ""
        except Exception:
            log.exception("Capture d'écran impossible")
            return None, "\n\nLa capture de l'écran a échoué : dis-le simplement à l'utilisateur."
        finally:
            if cachee:
                self.fenetre.show()

    def _cacher_fenetre(self) -> bool:
        """Cache la fenêtre de Raya le temps de la capture ; vrai si elle était affichée."""
        try:
            fenetre = ctypes.windll.user32.FindWindowW(None, self.fenetre.title)
            if not fenetre or not ctypes.windll.user32.IsWindowVisible(fenetre) or ctypes.windll.user32.IsIconic(fenetre):
                return False
            self.fenetre.hide()
            time.sleep(0.4)  # le temps que Windows redessine ce qu'il y a derrière
            return True
        except Exception:
            log.exception("Impossible de cacher la fenêtre")
            return False

    def _redemarrer_moteur_si_besoin(self) -> None:
        try:
            httpx.get(f"{self._serveur.url}/health", timeout=3)
        except httpx.HTTPError:
            self._pret = False
            self._etat("demarrage", "Je redémarre, quelques secondes…")
            try:
                self._serveur.demarrer()
                self._agent.url = self._serveur.url
                self._pret = True
                self._etat("pret")
            except Exception as e:
                self._etat("erreur", f"Le moteur IA ne répond plus ({e}). Fermez puis relancez Raya.")

    def arreter_reponse(self) -> None:
        if self._agent:
            self._agent.annule = True
        self._lecteur.arreter()

    # ---------- voix ----------

    def _appui_parler(self) -> None:
        if not self._pret or not self._transcripteur:
            return
        self._lecteur.arreter()
        if self._en_reponse.locked() and self._agent:
            self._agent.annule = True  # parler interrompt la réponse en cours
        try:
            self._enregistreur.demarrer()
        except Exception:
            log.exception("Micro indisponible")
            self._js("notification", "Je n'arrive pas à utiliser le micro. Vérifiez qu'il est bien branché.")
            return
        bip(True)
        self._etat("ecoute")

    def _relache_parler(self) -> None:
        audio = self._enregistreur.arreter()
        if not self._pret:
            return
        bip(False)
        if audio is None:
            self._etat("pret")
            return
        self._etat("transcription")
        threading.Thread(target=self._transcrire, args=(audio,), daemon=True).start()

    def _transcrire(self, audio) -> None:
        try:
            # Le prénom et les contacts aident Whisper à reconnaître les noms (« envoie un mail à Nicole »)
            noms = [self.reglages.prenom, *(c["nom"] for c in self.memoire.contacts())]
            texte = self._transcripteur.transcrire(audio, noms)
        except Exception:
            log.exception("Transcription impossible")
            texte = ""
        if not texte:
            self._etat("pret")
            self._js("notification", "Je n'ai rien entendu. Maintenez la touche pendant que vous parlez.")
            return
        self._js("messageUtilisateur", texte)
        self.envoyer(texte, [], oral=True)

    # ---------- rappels de l'agenda ----------

    def _surveiller_rappels(self) -> None:
        while not self.quitter_demande:
            try:
                self.verifier_rappels()
            except Exception:
                log.exception("Vérification des rappels impossible")
            time.sleep(5)  # un minuteur de 30 secondes ne doit pas sonner avec 20 secondes de retard

    def verifier_rappels(self, maintenant: datetime | None = None) -> list[str]:
        """Annonce les rappels dont c'est l'heure ; regroupe ceux manqués pendant que Raya était fermée."""
        maintenant = maintenant or datetime.now()
        dus = self.agenda.rappels_dus(maintenant)
        annonces = []
        for r in (r for r in dus if not r["manque"]):
            if r["avance"] and r["quand"] > maintenant:
                annonces.append(f"Rappel : {r['titre']}, {dates.decrire(r['quand'], maintenant)}.")
            elif dates.MINUTEUR.search(dates._simplifier(r["titre"])):
                annonces.append(f"{r['titre']} : c'est terminé !")
            else:
                annonces.append(f"C'est l'heure : {r['titre']}.")
        manques = [r for r in dus if r["manque"]]
        if manques:
            liste = " ; ".join(f"{r['titre']} ({dates.decrire(r['quand'], maintenant)})" for r in manques)
            annonces.append(f"Rappel manqué pendant que Raya était fermée : {liste}.")
        for r in dus:
            self.agenda.marquer_rappele(r, maintenant)
        if annonces:
            self._annoncer(annonces)
        if dus:
            self._js("agendaModifie")
        return annonces

    def _annoncer(self, annonces: list[str]) -> None:
        """Bandeau et bulle pour chaque rappel, fenêtre au premier plan et alarme en boucle
        jusqu'à « J'ai compris » (1 minute au plus), puis la voix."""
        for texte in annonces:
            log.info("Rappel : %s", texte)
            self._js("rappel", texte)
            if self.notifier_windows:
                try:
                    self.notifier_windows(texte, "Raya Assistant — rappel")
                except Exception:
                    log.exception("Notification Windows impossible")
        self._premier_plan(True)

        def ensuite():
            self._premier_plan(False)
            self._lecteur.dire(" ".join(annonces))

        self.alarme.sonner(self.reglages.son_alarme, ensuite)

    def _premier_plan(self, actif: bool) -> None:
        """Pendant l'alarme, la fenêtre s'affiche par-dessus les autres programmes."""
        if not self.fenetre:
            return
        try:
            if actif:
                self.fenetre.show()
                self.fenetre.restore()
            self.fenetre.on_top = actif
        except Exception:
            log.exception("Impossible de mettre la fenêtre au premier plan")

    def contenu_agenda(self) -> list[dict]:
        maintenant = datetime.now()
        return [{"id": r["id"], "titre": r["titre"], "quand": dates.decrire(r["quand"], maintenant),
                 "repetition": dates.REPETITIONS.get(r["repetition"], ""),
                 "avance": outil_agenda._duree(r["avance"]) + " avant" if r["avance"] else ""}
                for r in self.agenda.a_venir(maintenant)]

    # ---------- mémoire ----------

    def _contexte_memoire(self) -> str:
        return (bloc_memoire(self.memoire.pour_prompt(), self.historique.resumes_recents(5),
                             [r["nom"] for r in self.memoire.raccourcis()], self.reglages.prenom,
                             bool(self.reglages.email))
                + bloc_fichiers_ouverts(ordinateur.fichiers_ouverts()))

    def _resumer_en_arriere_plan(self) -> None:
        threading.Thread(target=self._resumer_conversations, daemon=True).start()

    def _resumer_conversations(self) -> None:
        """Résume en une phrase les conversations terminées, quand Raya ne répond pas."""
        if not self._agent or not self._resume_en_cours.acquire(blocking=False):
            return
        try:
            for id_ in self.historique.a_resumer(sauf=self._id_conversation):
                messages = self.historique.charger(id_)
                if not any(m["role"] == "user" for m in messages):
                    self.historique.definir_resume(id_, "")
                    continue
                while not self._en_reponse.acquire(timeout=1):  # une réponse à l'utilisateur passe d'abord
                    if self.quitter_demande:
                        return
                try:
                    resume = masquer(self._agent.resumer(messages))
                except httpx.HTTPError:
                    log.warning("Résumé impossible pour la conversation %s", id_)
                    return
                finally:
                    self._en_reponse.release()
                self.historique.definir_resume(id_, resume)
                log.info("Résumé conversation %s : %s", id_, resume)
        finally:
            self._resume_en_cours.release()

    def contenu_memoire(self) -> dict:
        raccourcis = [{"id": r["id"], "nom": r["nom"], "actions": [souvenirs.decrire_action(a) for a in r["actions"]]}
                      for r in self.memoire.raccourcis()]
        return {"souvenirs": self.memoire.souvenirs(), "favoris": self.memoire.favoris(), "raccourcis": raccourcis,
                "contacts": self.memoire.contacts()}

    # ---------- conversations ----------

    def nouvelle_conversation(self) -> None:
        self.arreter_reponse()
        with self._en_reponse:
            self._messages = []
            self._id_conversation = None
            navigation.contexte.en_attente = ""
            outils.journal.clear()
        self._resumer_en_arriere_plan()

    def ouvrir_conversation(self, id_: int) -> list[dict]:
        self.arreter_reponse()
        with self._en_reponse:
            self._messages = self.historique.charger(id_)
            self._id_conversation = id_
            navigation.contexte.en_attente = ""
            outils.journal.clear()
        self._resumer_en_arriere_plan()
        return [m for m in self._messages if m["role"] in ("user", "assistant") and m.get("content")]

    def supprimer_conversation(self, id_: int) -> None:
        self.historique.supprimer(id_)
        if id_ == self._id_conversation:
            self.nouvelle_conversation()
        self._js("listeConversations", self.historique.lister())

    # ---------- réglages ----------

    def _reglages_pour_ui(self) -> dict:
        return {
            "touche": self.reglages.touche_parler,
            "toucheNom": nom_lisible(self.reglages.touche_parler),
            "voix": self.reglages.voix,
            "voixListe": VOIX_DISPONIBLES,
            "tailleTexte": self.reglages.taille_texte,
            "demarrerWindows": self.reglages.demarrer_avec_windows,
            "sonAlarme": self.reglages.son_alarme,
            "sonsAlarme": SONS,
            "messagerie": self.reglages.messagerie,
            "messageries": outil_email.MESSAGERIES,
            "prenom": self.reglages.prenom,
            "accueilFait": self.reglages.accueil_fait,
            "suggestions": accueil.suggestions(self.reglages.usages),
        }

    def modifier_reglages(self, valeurs: dict) -> dict:
        if "voix" in valeurs and valeurs["voix"] in VOIX_DISPONIBLES:
            self.reglages.voix = self._lecteur.voix = valeurs["voix"]
        if "tailleTexte" in valeurs:
            self.reglages.taille_texte = max(config.TAILLE_TEXTE_MIN, min(config.TAILLE_TEXTE_MAX,
                                                                   int(valeurs["tailleTexte"])))
        if "sonAlarme" in valeurs and (valeurs["sonAlarme"] in SONS or valeurs["sonAlarme"] == ""):
            self.reglages.son_alarme = valeurs["sonAlarme"]
        if valeurs.get("messagerie") in outil_email.MESSAGERIES:
            self.reglages.messagerie = valeurs["messagerie"]
        if "demarrerWindows" in valeurs:
            self.reglages.demarrer_avec_windows = bool(valeurs["demarrerWindows"])
            demarrage.appliquer(self.reglages.demarrer_avec_windows)
        self.reglages.enregistrer()
        return self._reglages_pour_ui()

    def capturer_touche(self) -> None:
        if not self._touche:
            self._js("notification", "La voix n'est pas encore prête.")
            return

        def capturee(nom: str):
            self.reglages.touche_parler = nom
            self.reglages.enregistrer()
            self._js("appliquerReglages", self._reglages_pour_ui())
            self._etat("pret" if self._pret else "demarrage")

        self._touche.capturer_prochaine_touche(capturee)


class Api:
    """Fonctions appelables depuis l'interface (window.pywebview.api.*)."""

    def __init__(self, app: Application):
        self._app = app

    def envoyer(self, texte, fichiers):
        self._app.envoyer(texte, fichiers or [])

    def arreter(self):
        self._app.arreter_reponse()

    def micro_appui(self):
        self._app._appui_parler()

    def micro_relache(self):
        self._app._relache_parler()

    def lire(self, texte):
        self._app._lecteur.dire(texte)

    def arreter_voix(self):
        self._app._lecteur.arreter()

    def nouvelle_conversation(self):
        self._app.nouvelle_conversation()

    def ouvrir_conversation(self, id_):
        return self._app.ouvrir_conversation(int(id_))

    def supprimer_conversation(self, id_):
        self._app.supprimer_conversation(int(id_))

    def choisir_fichiers(self):
        resultat = self._app.fenetre.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True,
            file_types=("Documents (*.docx;*.odt;*.pdf;*.xlsx;*.xlsm;*.xls;*.ods;*.csv;*.txt)", "Tous les fichiers (*.*)"))
        self._app._joindre(list(resultat or []))

    def ouvrir_fichier(self, chemin):
        p = Path(chemin)
        if p.suffix.lower() in EXTENSIONS_JOINTES and p.is_file():
            os.startfile(p)

    def ouvrir_dossier(self, chemin=""):
        if chemin and Path(chemin).is_file():
            subprocess.Popen(["explorer", f"/select,{Path(chemin)}"])
        else:
            config.DOSSIER_DOCUMENTS.mkdir(parents=True, exist_ok=True)
            os.startfile(config.DOSSIER_DOCUMENTS)

    def ouvrir_lien(self, url):
        if str(url).startswith(("http://", "https://")):
            navigation.contexte.en_attente = ""
            webbrowser.open(url)

    def memoire(self):
        return self._app.contenu_memoire()

    def supprimer_souvenir(self, id_):
        self._app.memoire.supprimer_souvenir(int(id_))
        return self._app.contenu_memoire()

    def tout_oublier(self):
        self._app.memoire.tout_oublier()
        return self._app.contenu_memoire()

    def ajouter_favori(self, nom, url):
        try:
            self._app.memoire.ajouter_favori(str(nom), str(url))
        except ValueError as e:
            return {**self._app.contenu_memoire(), "erreur": str(e)}
        return self._app.contenu_memoire()

    def supprimer_raccourci(self, id_):
        self._app.memoire.supprimer_raccourci(int(id_))
        return self._app.contenu_memoire()

    def agenda(self):
        return self._app.contenu_agenda()

    def accueil(self):
        r = self._app.reglages
        return {"prenom": r.prenom, "email": r.email, "usagesChoisis": r.usages,
                "usages": [{"id": f["id"], "emoji": f["emoji"], "titre": f["titre"]} for f in accueil.FONCTIONS]}

    def apercu(self, usages=None):
        return accueil.apercu(list(usages or []))

    def enregistrer_accueil(self, prenom, email, usages):
        erreur = accueil.enregistrer(self._app.reglages, self._app.memoire, prenom, email, list(usages or []))
        if erreur:
            return {"erreur": erreur}
        self._app._js("appliquerReglages", self._app._reglages_pour_ui())
        return {"ok": True}

    def arreter_alarme(self):
        self._app.alarme.arreter()

    def essayer_alarme(self, son):
        Alarme.essayer(str(son))

    def supprimer_rendez_vous(self, id_):
        self._app.agenda.supprimer(int(id_))
        return self._app.contenu_agenda()

    def ajouter_contact(self, nom, email, telephone=""):
        try:
            self._app.memoire.ajouter_contact(str(nom), str(email or ""), str(telephone or ""))
        except ValueError as e:
            return {**self._app.contenu_memoire(), "erreurContact": str(e)}
        return self._app.contenu_memoire()

    def supprimer_contact(self, id_):
        self._app.memoire.supprimer_contact(int(id_))
        return self._app.contenu_memoire()

    def supprimer_favori(self, id_):
        self._app.memoire.supprimer_favori(int(id_))
        return self._app.contenu_memoire()

    def reglages(self, valeurs=None):
        return self._app.modifier_reglages(valeurs or {})

    def capturer_touche(self):
        self._app.capturer_touche()

    def lancer_telechargement(self):
        self._app._telechargement.set()
