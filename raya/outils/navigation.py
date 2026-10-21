"""Outil « ouvrir_site » : ouvrir un site (favori, site connu, adresse) ou une recherche dans le navigateur.

Un site inconnu trouvé par recherche n'est jamais ouvert directement : on le propose à
l'utilisateur, qui confirme par un bouton (ou en répondant « oui »).
"""
import re
import time
import webbrowser
from urllib.parse import quote_plus, urlparse

from ddgs import DDGS

from raya.outils import fichiers
from raya.outils.fichiers import ErreurOutil
from raya.stockage.memoire import Memoire, normaliser

MARQUE_PROPOSITION = "[proposition de site : {url} | {titre}]"

# Sites connus et sûrs, ouverts sans confirmation
SITES_CONNUS = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.fr",
    "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
    "gmail": "https://mail.google.com",
    "outlook": "https://outlook.live.com",
    "hotmail": "https://outlook.live.com",
    "wikipedia": "https://fr.wikipedia.org",
    "ameli": "https://www.ameli.fr",
    "caf": "https://www.caf.fr",
    "impots": "https://www.impots.gouv.fr",
    "service public": "https://www.service-public.fr",
    "france travail": "https://www.francetravail.fr",
    "pole emploi": "https://www.francetravail.fr",
    "la poste": "https://www.laposte.fr",
    "meteo france": "https://meteofrance.com",
    "meteo": "https://meteofrance.com",
    "doctolib": "https://www.doctolib.fr",
    "sncf": "https://www.sncf-connect.com",
    "leboncoin": "https://www.leboncoin.fr",
    "le bon coin": "https://www.leboncoin.fr",
    "amazon": "https://www.amazon.fr",
    "facebook": "https://www.facebook.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "france info": "https://www.francetvinfo.fr",
    "le monde": "https://www.lemonde.fr",
}

RECHERCHES = {
    "youtube": "https://www.youtube.com/results?search_query={}",
    "google": "https://www.google.fr/search?q={}",
    "images": "https://www.google.fr/search?tbm=isch&q={}",
    "google maps": "https://www.google.com/maps/search/{}",
    "maps": "https://www.google.com/maps/search/{}",
    "carte": "https://www.google.com/maps/search/{}",
    "wikipedia": "https://fr.wikipedia.org/w/index.php?search={}",
    "leboncoin": "https://www.leboncoin.fr/recherche?text={}",
    "le bon coin": "https://www.leboncoin.fr/recherche?text={}",
    "amazon": "https://www.amazon.fr/s?k={}",
}

ADRESSE = re.compile(r"^(https?://)?([\w-]+\.)+[a-z]{2,}(/\S*)?$", re.I)
OUI = re.compile(r"\b(oui|ouais|ouvre|ouvrez|vas[- ]y|allez[- ]y|d'accord|ok|okay|c'est (bon|ça)|exact|volontiers)\b", re.I)


class Contexte:
    """Ce que l'outil doit savoir de la conversation, renseigné par l'application avant chaque réponse."""
    derniere_demande: str = ""
    en_attente: str = ""  # adresse proposée, en attente de confirmation
    demande_proposition: str = ""  # message qui a mené à la proposition (ce n'est pas une confirmation)


contexte = Contexte()
_memoire: Memoire | None = None


def configurer(memoire: Memoire) -> None:
    global _memoire
    _memoire = memoire


def domaine(url: str) -> str:
    return (urlparse(url if "://" in url else "https://" + url).hostname or "").removeprefix("www.")


def _ouvrir(url: str) -> None:
    if fichiers.OUVRIR_AUTOMATIQUEMENT:
        webbrowser.open(url)


def _cles(site: str) -> list[str]:
    """Variantes du nom à chercher : « le site de La Poste » → [« le site de la poste », « la poste », « poste »]."""
    brut = re.sub(r" (fr|com|gouv fr|org)$", "", normaliser(site)).strip()
    sans_site = re.sub(r"^(le |la |les )?(site )?(internet )?(de |du |des |d )", "", brut).strip()
    sans_article = re.sub(r"^(la |le |l |les )", "", sans_site).strip()
    return list(dict.fromkeys(c for c in (brut, sans_site, sans_article) if c))


def _chercher(table: dict, site: str) -> str | None:
    return next((c for c in _cles(site) if c in table), None)


def ouvrir_site(site: str = "", recherche: str = "") -> str:
    site, recherche = (site or "").strip(), (recherche or "").strip()

    # 1. Recherche directe sur un site connu (YouTube, Google, Maps…)
    if recherche:
        cle = _chercher(RECHERCHES, site) or "google"
        _ouvrir(RECHERCHES[cle].format(quote_plus(recherche)))
        ou = "Google" if cle == "google" else cle.title()
        return f"Recherche « {recherche} » ouverte sur {ou} dans le navigateur."

    if not site:
        raise ErreurOutil("Indique le nom ou l'adresse du site à ouvrir.")

    # 2. Favoris de l'utilisateur
    if _memoire and (favori := _memoire.trouver_favori(site)):
        _ouvrir(favori["url"])
        return f"Le site favori « {favori['nom']} » ({domaine(favori['url'])}) est ouvert dans le navigateur."

    # 3. Sites connus
    if cle := _chercher(SITES_CONNUS, site):
        _ouvrir(SITES_CONNUS[cle])
        return f"Le site {domaine(SITES_CONNUS[cle])} est ouvert dans le navigateur."

    # 4. Adresse précise : ouverte si l'utilisateur l'a lui-même donnée, ou s'il vient de confirmer
    if ADRESSE.match(site):
        url = site if site.lower().startswith("http") else "https://" + site
        dom = domaine(url)
        donnee_par_utilisateur = dom and dom in contexte.derniere_demande.lower()
        confirmee = (contexte.en_attente and domaine(contexte.en_attente) == dom
                     and contexte.derniere_demande != contexte.demande_proposition
                     and OUI.search(contexte.derniere_demande))
        if donnee_par_utilisateur or confirmee:
            contexte.en_attente = ""
            _ouvrir(url)
            return f"Le site {dom} est ouvert dans le navigateur."
        return _proposer(url, dom)

    # 5. Site inconnu : on cherche l'adresse officielle, puis on demande confirmation
    resultats = None
    for essai in range(2):  # le moteur de recherche échoue parfois ponctuellement
        try:
            resultats = DDGS().text(f"{site} site officiel", region="fr-fr", max_results=5)
            break
        except Exception as e:
            if essai == 1:
                raise ErreurOutil("La recherche du site n'a pas fonctionné. Propose à l'utilisateur de réessayer "
                                  "ou de donner l'adresse exacte du site.") from e
            time.sleep(1)
    for r in resultats or []:
        url = r.get("href", "")
        if url.startswith("http"):
            return _proposer(url, r.get("title", "") or domaine(url))
    raise ErreurOutil("Je n'ai pas trouvé ce site. Demande à l'utilisateur son adresse exacte (par exemple www.exemple.fr).")


def _proposer(url: str, titre: str) -> str:
    contexte.en_attente = url
    contexte.demande_proposition = contexte.derniere_demande
    titre = titre.replace("|", "-").replace("]", ")")
    return (MARQUE_PROPOSITION.format(url=url, titre=titre) + f" Je ne l'ai PAS encore ouvert : c'est l'adresse {domaine(url)}. "
            "Un bouton « Ouvrir » est affiché sous ta réponse. Dis à l'utilisateur quel site tu as trouvé "
            "et demande-lui de cliquer sur le bouton ou de répondre « oui » pour l'ouvrir.")


SCHEMAS = [
    {
        "name": "ouvrir_site",
        "description": (
            "Ouvre un site internet dans le navigateur de l'utilisateur : par son nom (« YouTube », « la CAF », "
            "« ma banque » pour un favori) ou son adresse. Avec « recherche », ouvre directement les résultats "
            "d'une recherche (ex. site=YouTube, recherche=recette de crêpes ; site=Maps, recherche=pharmacie Lyon). "
            "À utiliser quand l'utilisateur veut VOIR un site, pas pour lui donner une information."),
        "parameters": {
            "type": "object",
            "properties": {
                "site": {"type": "string", "description": "Nom ou adresse du site"},
                "recherche": {"type": "string", "description": "Ce qu'il faut chercher sur ce site (facultatif)"},
            },
            "required": ["site"],
        },
    },
]

FONCTIONS = {"ouvrir_site": ouvrir_site}
